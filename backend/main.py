from datetime import datetime
from io import BytesIO, StringIO
import csv
import logging
import os
import pandas as pd
import requests
from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import ROOT, MAX_UPLOAD_BYTES, CORS_ORIGINS
from .database import Base, engine, get_db
from .models import Building, ConsumptionRecord, Simulation, Conversation
from .services import forecast, detect_anomalies
from .assistant import answer_question, LANGUAGES
from integrations.gnani.prisma import transcribe
from integrations.gnani.timbre import synthesize
from backend.reports import create_summary_pdf

SERVICE_STATUS = {}

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ecowatt")
Base.metadata.create_all(bind=engine)
app = FastAPI(title="EcoWatt", version="1.0.0", description="Energy analytics from explicitly imported meter data.")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=False, allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["*"])

class BuildingIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    building_type: str = Field(default="Unspecified", max_length=80)
    location: str = Field(default="", max_length=120)
    floor_area_m2: float | None = Field(default=None, gt=0)

class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    building_id: int | None = None
    previous_question: str = Field(default="", max_length=1000)
    language: Literal["en-IN", "hi-IN", "hi-en", "pa-IN"] = "en-IN"
    tariff: float | None = Field(default=None, ge=0)

class SpeechIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    language: Literal["en-IN", "hi-IN", "hi-en", "pa-IN"] = "en-IN"

class SimIn(BaseModel):
    building_id: int
    name: str = Field(default="Untitled scenario", max_length=120)
    reduction_pct: float = Field(ge=0, le=100)
    tariff: float | None = Field(default=None, ge=0)

@app.get("/")
def index(): return FileResponse(ROOT / "frontend" / "index.html")

@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    return {"status": "ok", "database": "connected", "records": db.query(ConsumptionRecord).count(), "mode": "live-data" if db.query(ConsumptionRecord).count() else "awaiting-data"}

@app.get("/api/buildings")
def buildings(db: Session = Depends(get_db)):
    return [{"id": b.id, "name": b.name, "building_type": b.building_type, "location": b.location, "floor_area_m2": b.floor_area_m2, "records": len(b.records)} for b in db.scalars(select(Building).order_by(Building.name))]

@app.post("/api/buildings", status_code=201)
def add_building(body: BuildingIn, db: Session = Depends(get_db)):
    if db.scalar(select(Building).where(Building.name == body.name)):
        raise HTTPException(409, "A building with that name already exists.")
    obj = Building(**body.model_dump()); db.add(obj); db.commit(); db.refresh(obj)
    return {"id": obj.id, "name": obj.name, "building_type": obj.building_type, "location": obj.location, "floor_area_m2": obj.floor_area_m2, "records": 0}

@app.put("/api/buildings/{building_id}")
def edit_building(building_id: int, body: BuildingIn, db: Session = Depends(get_db)):
    obj = db.get(Building, building_id)
    if not obj: raise HTTPException(404, "Building not found")
    obj.name, obj.building_type, obj.location, obj.floor_area_m2 = body.name, body.building_type, body.location, body.floor_area_m2
    db.commit(); return {"id": obj.id, "name": obj.name}

@app.delete("/api/buildings/{building_id}", status_code=204)
def delete_building(building_id: int, db: Session = Depends(get_db)):
    obj = db.get(Building, building_id)
    if not obj: raise HTTPException(404, "Building not found")
    db.delete(obj); db.commit(); return Response(status_code=204)

def rows_for(db, building_id):
    query = select(ConsumptionRecord).where(ConsumptionRecord.building_id == building_id).order_by(ConsumptionRecord.timestamp)
    return list(db.scalars(query))

@app.get("/api/dashboard/summary")
def summary(building_id: int | None = None, tariff: float = 0, db: Session = Depends(get_db)):
    bs = list(db.scalars(select(Building).order_by(Building.name)))
    if building_id is None and bs: building_id = bs[0].id
    b = db.get(Building, building_id) if building_id else None
    records = rows_for(db, building_id) if b else []
    if not records: return {"building": {"id": b.id, "name": b.name} if b else None, "available": False, "message": "Import meter readings to see measured analytics.", "record_count": 0, "unit": None, "metrics": None, "series": [], "models": None}
    unit = records[0].unit
    if any(r.unit != unit for r in records): raise HTTPException(422, "This building contains mixed units; normalize them before analysis.")
    if unit.lower() not in {"kwh", "wh"}: raise HTTPException(422, "Cost and forecasting currently require energy units kWh or Wh. Convert only when the source supports it.")
    values = [r.value / 1000 if unit.lower() == "wh" else r.value for r in records]
    latest_time = records[-1].timestamp
    recent = [v for r,v in zip(records, values) if latest_time - pd.Timedelta(hours=24) < r.timestamp <= latest_time]
    previous = [v for r,v in zip(records, values) if latest_time - pd.Timedelta(hours=48) < r.timestamp <= latest_time - pd.Timedelta(hours=24)]
    delta = (sum(recent)/sum(previous)-1)*100 if previous and sum(previous) else None
    series = [{"timestamp": r.timestamp.isoformat(), "value": round(v, 4)} for r, v in zip(records[-5000:], values[-5000:])]
    fc = forecast(values, horizon=24, timestamps=[r.timestamp for r in records])
    anomaly_records = [{"timestamp": r.timestamp.isoformat(), "value": v} for r, v in zip(records, values)]
    return {"building": {"id": b.id, "name": b.name, "building_type":b.building_type, "location":b.location, "floor_area_m2":b.floor_area_m2}, "available": True, "record_count": len(records), "unit": "kWh" if unit.lower() in {"kwh","wh"} else unit,
      "coverage": {"from": records[0].timestamp.isoformat(), "to": records[-1].timestamp.isoformat()},
      "metrics": {"latest": round(values[-1],3), "last_24h": round(sum(recent),3), "total_energy": round(sum(values),3), "previous_24h": round(sum(previous),3) if previous else None, "change_pct": round(delta,1) if delta is not None else None, "cost_24h": round(sum(recent)*tariff,2) if tariff else None, "tariff": tariff, "peak": round(max(values),3)},
      "series": series, "forecast": fc, "anomalies": detect_anomalies(anomaly_records)[-8:], "models": fc.get("metrics")}

@app.get("/api/analytics")
def analytics(building_id: int, tariff: float = 0, db: Session = Depends(get_db)):
    s = summary(building_id, tariff, db)
    if not s["available"]: return s
    return {"building":s["building"], "coverage":s["coverage"], "unit":s["unit"], "metrics":s["metrics"], "daily":daily_totals(rows_for(db,building_id))}

def daily_totals(rows):
    agg={}
    for r in rows: agg.setdefault(r.timestamp.date().isoformat(),0); agg[r.timestamp.date().isoformat()]+=r.value/1000 if r.unit.lower()=="wh" else r.value
    return [{"date":k,"value":round(v,3)} for k,v in sorted(agg.items())]

@app.get("/api/forecast")
def get_forecast(building_id: int, horizon: int = 7, db: Session = Depends(get_db)):
    if not 1 <= horizon <= 30: raise HTTPException(422, "Horizon must be 1–30 hours")
    rows=rows_for(db,building_id)
    if not rows: return {"available":False,"reason":"No meter records found."}
    return forecast([r.value/1000 if r.unit.lower()=="wh" else r.value for r in rows],horizon,[r.timestamp for r in rows])

@app.get("/api/anomalies")
def anomalies(building_id: int, db: Session = Depends(get_db)):
    rows=rows_for(db,building_id)
    return detect_anomalies([{"timestamp":r.timestamp.isoformat(),"value":r.value/1000 if r.unit.lower()=="wh" else r.value} for r in rows])

@app.get("/api/recommendations")
def recommendations(building_id: int, db: Session = Depends(get_db)):
    rows=rows_for(db,building_id)
    if len(rows)<48: return {"available":False,"items":[],"message":"At least two days of readings are needed for evidence-based patterns."}
    values=pd.Series([r.value/1000 if r.unit.lower()=="wh" else r.value for r in rows], index=pd.to_datetime([r.timestamp for r in rows]))
    by_hour=values.groupby(values.index.hour).mean()
    off_hours=float(by_hour.loc[by_hour.index.isin([0,1,2,3,4,5])].mean())
    peak_hour=int(by_hour.idxmax())
    return {"available":True,"items":[{"title":"Review recurring peak-hour operations","reason":f"Average metered use is highest around {peak_hour:02d}:00 in this dataset.","evidence":{"peak_hour":peak_hour,"average_at_peak":round(float(by_hour.max()),3),"unit":"kWh per record"},"priority":"review","suggested_action":"Check schedules, occupancy and equipment operation around this hour. Validate against site operations before changing settings.","estimated_savings":None,"assumptions":"Hourly meter data indicates timing only; end-use attribution and savings cannot be inferred from a whole-building meter."}]}

@app.post("/api/data/preview")
async def preview(file: UploadFile=File(...)):
    content=await file.read(MAX_UPLOAD_BYTES+1)
    if len(content)>MAX_UPLOAD_BYTES: raise HTTPException(413,"CSV exceeds 10 MiB limit")
    if not file.filename.lower().endswith(".csv"): raise HTTPException(415,"Upload a .csv file")
    try: frame=pd.read_csv(BytesIO(content), nrows=10000)
    except Exception as exc: raise HTTPException(400,f"Could not read CSV: {exc}")
    if frame.empty: raise HTTPException(400,"CSV contains no records")
    return {"filename":file.filename,"columns":[str(c) for c in frame.columns],"preview":frame.head(8).where(pd.notna(frame.head(8)),None).to_dict(orient="records"),"rows_scanned":len(frame),"duplicate_rows":int(frame.duplicated().sum()),"missing_cells":int(frame.isna().sum().sum())}

@app.get("/api/data/sample")
def sample_dataset():
    path=ROOT / "data" / "bdg2_education_sample.csv"
    if not path.exists(): raise HTTPException(404,"The optional BDG2 sample CSV is not installed")
    return FileResponse(path,media_type="text/csv",filename="bdg2_education_sample.csv")

@app.get("/api/data/export")
def export_data(building_id: int, db: Session=Depends(get_db)):
    building=db.get(Building,building_id)
    if not building: raise HTTPException(404,"Building not found")
    records=rows_for(db,building_id)
    if not records: raise HTTPException(422,"No imported records are available to export")
    output=StringIO(newline="")
    writer=csv.writer(output)
    writer.writerow(["timestamp","value","unit"])
    writer.writerows((r.timestamp.isoformat(),r.value,r.unit) for r in records)
    return Response(content=output.getvalue(),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":f"attachment; filename=ecowatt-{building_id}-meter-data.csv"})

@app.post("/api/data/upload",status_code=201)
async def upload(file: UploadFile=File(...), building_id: int=Form(...), timestamp_column: str=Form(...), value_column: str=Form(...), unit: str=Form(...), db: Session=Depends(get_db)):
    if unit not in {"kWh","Wh","kW"}: raise HTTPException(422,"Choose kWh, Wh or kW; power kW cannot be converted to energy without an interval.")
    building=db.get(Building,building_id)
    if not building: raise HTTPException(404,"Building not found")
    if not file.filename.lower().endswith(".csv"): raise HTTPException(415,"Upload a .csv file")
    content=await file.read(MAX_UPLOAD_BYTES+1)
    if len(content)>MAX_UPLOAD_BYTES: raise HTTPException(413,"CSV exceeds 10 MiB limit")
    try: frame=pd.read_csv(BytesIO(content))
    except Exception as exc: raise HTTPException(400,f"Could not read CSV: {exc}")
    if timestamp_column not in frame or value_column not in frame: raise HTTPException(422,"Selected columns were not found")
    timestamps=pd.to_datetime(frame[timestamp_column],errors="coerce",utc=True)
    values=pd.to_numeric(frame[value_column],errors="coerce")
    clean=pd.DataFrame({"timestamp":timestamps,"value":values}).dropna().drop_duplicates(subset="timestamp").sort_values("timestamp")
    if clean.empty: raise HTTPException(422,"No valid timestamp and numeric value pairs were found")
    if (clean.value<0).any(): raise HTTPException(422,"Negative consumption records found. Correct the source before importing.")
    existing=set(r.timestamp for r in db.scalars(select(ConsumptionRecord.timestamp).where(ConsumptionRecord.building_id==building_id)))
    new=[ConsumptionRecord(building_id=building_id,timestamp=ts.to_pydatetime().replace(tzinfo=None),value=float(v),unit=unit,source=file.filename) for ts,v in zip(clean.timestamp,clean.value) if ts.to_pydatetime().replace(tzinfo=None) not in existing]
    if not new: raise HTTPException(409,"All valid timestamps already exist for this building")
    db.add_all(new); db.commit()
    return {"imported":len(new),"invalid_rows":int(len(frame)-len(clean)),"unit":unit,"building":building.name,"first_timestamp":new[0].timestamp.isoformat(),"last_timestamp":new[-1].timestamp.isoformat()}

@app.get("/api/simulations")
def list_simulations(building_id: int, db: Session=Depends(get_db)):
    return [{"id":s.id,"name":s.name,"baseline_kwh":s.baseline_kwh,"scenario_kwh":s.scenario_kwh,"assumptions":s.assumptions,"created_at":s.created_at.isoformat()} for s in db.scalars(select(Simulation).where(Simulation.building_id==building_id).order_by(Simulation.created_at.desc()))]

@app.post("/api/simulations",status_code=201)
def simulate(body: SimIn,db: Session=Depends(get_db)):
    rows=rows_for(db,body.building_id)
    if not rows: raise HTTPException(422,"Import meter readings before running a scenario")
    baseline=sum(r.value/1000 if r.unit.lower()=="wh" else r.value for r in rows)
    scenario=baseline*(1-body.reduction_pct/100)
    assumptions=f"User-selected whole-building reduction of {body.reduction_pct:g}%; applied uniformly to {len(rows)} records. This is a scenario assumption, not a measured HVAC or lighting effect. Tariff={body.tariff if body.tariff is not None else 'not provided'}"
    obj=Simulation(building_id=body.building_id,name=body.name,baseline_kwh=baseline,scenario_kwh=scenario,assumptions=assumptions)
    db.add(obj); db.commit(); db.refresh(obj)
    return {"id":obj.id,"baseline_kwh":round(baseline,3),"scenario_kwh":round(scenario,3),"energy_savings_kwh":round(baseline-scenario,3),"percent_change":body.reduction_pct,"baseline_cost":round(baseline*body.tariff,2) if body.tariff is not None else None,"scenario_cost":round(scenario*body.tariff,2) if body.tariff is not None else None,"assumptions":assumptions}

@app.get("/api/assistant/status")
def assistant_status():
    return {"mode":"analytics from imported data; Gnani voice services optional","services":{"prisma":SERVICE_STATUS.get("prisma", "Configured · not tested" if os.getenv("GNANI_PRISMA_API_KEY") else "Not Configured"),"evon":"Not Configured","timbre":SERVICE_STATUS.get("timbre", "Configured · not tested" if os.getenv("GNANI_TIMBRE_API_KEY") else "Not Configured")},"demo_mode":"No synthetic meter data; use the attributed BDG2 sample or import your own."}

@app.post("/api/assistant/chat")
def chat(body: ChatIn,db: Session=Depends(get_db)):
    b=db.get(Building,body.building_id) if body.building_id else db.scalar(select(Building).order_by(Building.id))
    if not b:
        answer={"en-IN":"Add a building and import meter readings first. I can only answer from EcoWatt data.","hi-IN":"पहले भवन जोड़ें और मीटर रीडिंग आयात करें। मैं केवल EcoWatt के डेटा से उत्तर दे सकता हूं।","hi-en":"Pehle building add karke meter readings import karein. Main sirf EcoWatt ke data se jawab de sakta hoon.","pa-IN":"ਪਹਿਲਾਂ ਇਮਾਰਤ ਜੋੜੋ ਅਤੇ ਮੀਟਰ ਰੀਡਿੰਗਾਂ ਆਯਾਤ ਕਰੋ। ਮੈਂ ਸਿਰਫ਼ EcoWatt ਦੇ ਡਾਟਾ ਤੋਂ ਜਵਾਬ ਦੇ ਸਕਦਾ ਹਾਂ."}[body.language]
    else:
        data=summary(b.id,0,db)
        if not data["available"]:
            answer={"en-IN":f"{b.name} has no imported meter readings yet. Upload a CSV to enable data-backed answers.","hi-IN":f"{b.name} में अभी मीटर रीडिंग आयात नहीं हुई हैं। डेटा-आधारित उत्तरों के लिए CSV अपलोड करें।","hi-en":f"{b.name} mein abhi meter readings import nahi hui hain. Data-based answers ke liye CSV upload karein.","pa-IN":f"{b.name} ਵਿੱਚ ਹਾਲੇ ਮੀਟਰ ਰੀਡਿੰਗਾਂ ਆਯਾਤ ਨਹੀਂ ਹੋਈਆਂ। ਡਾਟਾ-ਅਧਾਰਿਤ ਜਵਾਬਾਂ ਲਈ CSV ਅਪਲੋਡ ਕਰੋ."}[body.language]
        else:
            recs=recommendations(b.id,db)
            intent,answer=answer_question(body.question,body.previous_question,body.language,b,rows_for(db,b.id),data,body.tariff,recs)
    db.add(Conversation(user_text=body.question,assistant_text=answer)); db.commit()
    return {"answer":answer,"source":"EcoWatt analytics","building":b.name if b else None,"intent":intent if b and data.get("available") else "setup","language":body.language}

@app.get("/api/assistant/history")
def history(db: Session=Depends(get_db)):
    return [{"question":x.user_text,"answer":x.assistant_text,"created_at":x.created_at.isoformat()} for x in db.scalars(select(Conversation).order_by(Conversation.created_at.desc()).limit(50))]

@app.post("/api/assistant/voice")
async def voice(file: UploadFile=File(...),language: str=Form("en-IN")):
    key=os.getenv("GNANI_PRISMA_API_KEY")
    if not key: raise HTTPException(503,"Prisma is Not Configured. Use the text assistant or add GNANI_PRISMA_API_KEY to backend environment.")
    if language not in LANGUAGES: raise HTTPException(422,"Choose English, Hindi, Hinglish or Punjabi.")
    allowed_audio={"audio/wav","audio/x-wav","audio/mpeg","audio/ogg","audio/flac","audio/aac","audio/mp4","audio/x-m4a"}
    if file.content_type not in allowed_audio: raise HTTPException(415,"Gnani Prisma accepts WAV, MP3, OGG, FLAC, AAC or M4A audio. This browser recording format is unsupported; use text chat.")
    content=await file.read(10*1024*1024+1)
    if not content or len(content)>10*1024*1024: raise HTTPException(413,"Audio must be non-empty and under 10 MiB")
    try:
        stt_language={"en-IN":"en-IN","hi-IN":"hi-IN","hi-en":"hi-IN,en-IN","pa-IN":"pa-IN"}[language]
        result=transcribe(content,file.filename or "question.ogg",file.content_type, key, language_code=stt_language, output_format="codemix" if language=="hi-en" else "verbatim")
        SERVICE_STATUS["prisma"]="Connected"
        return {"transcript":result["transcript"],"detected_language":result.get("detected_language_code"),"language":language,"service":"Prisma","status":"Connected"}
    except requests.HTTPError as exc:
        code=exc.response.status_code if exc.response is not None else 0
        SERVICE_STATUS["prisma"]="Authentication Failed" if code in (401,403) else "Request Failed"
        log.warning("Prisma request failed: HTTP %s",code or "unknown")
        raise HTTPException(502,"Gnani Prisma rejected the request; verify the API key, language and audio format.")
    except requests.RequestException as exc:
        log.warning("Prisma request failed: %s",type(exc).__name__)
        SERVICE_STATUS["prisma"]="Service Unavailable" if isinstance(exc,(requests.Timeout,requests.ConnectionError)) else "Request Failed"
        raise HTTPException(502,"Gnani Prisma request failed; check service availability and audio format")
    except ValueError as exc:
        SERVICE_STATUS["prisma"]="Request Failed"
        log.warning("Prisma response did not include a transcript")
        raise HTTPException(502,"Gnani Prisma returned no transcript. Try recording a clearer, shorter question.")

@app.post("/api/assistant/speech")
def assistant_speech(body: SpeechIn):
    key=os.getenv("GNANI_TIMBRE_API_KEY")
    if not key: raise HTTPException(503,"Timbre is Not Configured. Add GNANI_TIMBRE_API_KEY to the backend environment.")
    try:
        voices={"en-IN":"Kaveri","hi-IN":"Nalini","hi-en":"Poorvi","pa-IN":"Mehuli"}
        audio,content_type=synthesize(body.text,key,voice=voices[body.language],language=body.language)
        SERVICE_STATUS["timbre"]="Connected"
        return Response(content=audio,media_type=content_type or "audio/wav")
    except requests.HTTPError as exc:
        SERVICE_STATUS["timbre"]="Authentication Failed" if exc.response is not None and exc.response.status_code==401 else "Request Failed"
        log.warning("Timbre request failed: HTTP %s",exc.response.status_code if exc.response is not None else "unknown")
        raise HTTPException(502,"Gnani Timbre request failed")
    except requests.RequestException as exc:
        SERVICE_STATUS["timbre"]="Service Unavailable" if isinstance(exc,(requests.Timeout,requests.ConnectionError)) else "Request Failed"
        log.warning("Timbre request failed: %s",type(exc).__name__)
        raise HTTPException(502,"Gnani Timbre service is unavailable")

@app.get("/api/reports")
def report(building_id:int,tariff:float=0,db:Session=Depends(get_db)):
    s=summary(building_id,tariff,db)
    if not s["available"]: raise HTTPException(422,s["message"])
    s["recommendations"]=recommendations(building_id,db)
    s["simulations"]=list_simulations(building_id,db)
    pdf=create_summary_pdf(s)
    return Response(content=pdf,media_type="application/pdf",headers={"Content-Disposition":f"attachment; filename=ecowatt-{building_id}-summary.pdf"})

@app.get("/api/models/performance")
def performance(building_id:int,db:Session=Depends(get_db)):
    rows=rows_for(db,building_id)
    return forecast([r.value/1000 if r.unit.lower()=="wh" else r.value for r in rows],1,[r.timestamp for r in rows])

app.mount("/",StaticFiles(directory=ROOT/"frontend",html=True),name="frontend")
