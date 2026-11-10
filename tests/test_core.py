from datetime import datetime, timedelta
from backend.main import app, health, summary
from backend.database import SessionLocal
from backend.services import forecast, detect_anomalies

def test_startup_and_empty_dashboard():
    assert any(getattr(route, 'path', None) == '/api/health' for route in app.routes)
    db=SessionLocal()
    try:
        assert health(db)['status'] == 'ok'
        assert isinstance(summary(None, 0, db)['available'], bool)
    finally: db.close()

def test_forecast_requires_sufficient_history():
    assert forecast([1, 2, 3])['available'] is False

def test_forecast_has_evaluation_metrics():
    start=datetime(2024,1,1)
    vals=[10 + (i % 24) * .1 for i in range(120)]
    times=[start+timedelta(hours=i) for i in range(len(vals))]
    result=forecast(vals,3,times)
    assert result['available'] is True
    assert len(result['points']) == 3
    assert {'mae','rmse','r2'} <= result['metrics'].keys()

def test_anomaly_detector_flags_spike():
    rows=[{'timestamp':datetime(2024,1,1)+timedelta(hours=i),'value':10.0} for i in range(50)]
    rows[35]['value']=40
    assert any(x['observed'] == 40 for x in detect_anomalies(rows))

def test_tables_created_at_startup():
    from sqlalchemy import inspect
    from backend.database import engine
    assert {'buildings','consumption_records','simulations','conversations'} <= set(inspect(engine).get_table_names())

def test_bundled_dataset_is_a_substantial_hourly_subset():
    from pathlib import Path
    import pandas as pd
    path=Path(__file__).resolve().parents[1]/'data'/'bdg2_education_sample.csv'
    frame=pd.read_csv(path)
    assert list(frame.columns) == ['timestamp','consumption_kwh']
    assert len(frame) == 14156
    assert frame.timestamp.iloc[0] == '2016-05-01 19:00:00'

def test_report_builder_returns_pdf_bytes():
    from backend.reports import create_summary_pdf
    summary_data={
        'building':{'name':'Test building'},'coverage':{'from':'2024-01-01','to':'2024-01-03'},
        'metrics':{'latest':1.0,'last_24h':10.0,'previous_24h':9.0,'peak':3.0},
        'record_count':48,'forecast':{'available':False,'reason':'Insufficient history.'},
        'anomalies':[],'recommendations':{'items':[]},'simulations':[]}
    pdf=create_summary_pdf(summary_data)
    assert pdf.startswith(b'%PDF-')
    assert len(pdf)>1000
