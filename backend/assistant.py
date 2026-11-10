"""Deterministic, data-grounded intent handling for Ask EcoWatt."""
from __future__ import annotations

from datetime import timedelta
import re


LANGUAGES = {"en-IN", "hi-IN", "hi-en", "pa-IN"}


def _normal(value: str) -> str:
    return " ".join(value.lower().strip().split())


def classify_intent(question: str, previous_question: str = "") -> tuple[str, str]:
    """Return a specific intent and the text used for resolving follow-ups."""
    q = _normal(question)
    follow_up = len(q.split()) <= 7 and any(
        q.startswith(token) for token in ("what about", "how about", "and ", "also", "same for", "why", "how so", "aur ", "कल?", "yesterday?")
    )

    def match(text: str) -> str:
        # Specific intents take priority over broad words such as energy or usage.
        if re.search(r"(?<!\d)\d+(?:\.\d+)?\s*(?:%|percent\b|per cent\b|प्रतिशत)", text) or any(x in text for x in ("what if", "scenario", "simulate", "savings if", "if i reduce", "if we reduce", "agar ", "kam kar")):
            return "simulation"
        if any(x in text for x in ("recommend", "suggest", "optimi", "improve", "save energy", "reduce consumption", "reduce usage", "reduce energy", "बचत", "ਸੁਝਾਅ")):
            return "recommendation"
        if any(x in text for x in ("highest average", "hourly average", "average by hour", "average consumption by hour", "which hour", "किस घंटे", "ਕਿਹੜੇ ਘੰਟੇ")):
            return "hourly_average"
        if any(x in text for x in ("anomal", "unusual", "spike", "outlier", "असामान्य", "ਅਸਧਾਰਨ")):
            return "anomaly"
        if any(x in text for x in ("forecast", "predict", "next 24", "future", "agale", "अगले", "पूर्वानुमान", "ਅਗਲੇ")):
            return "forecast"
        if any(x in text for x in ("cost", "bill", "tariff", "electricity price", "बिल", "लागत", "ਬਿੱਲ", "ਲਾਗਤ")):
            return "cost"
        if any(x in text for x in ("compare", "comparison", "versus", "vs.", "previous period", "preceding period", "तुलना", "ਮੁਕਾਬਲਾ")):
            return "comparison"
        if any(x in text for x in ("peak", "highest use", "most electricity", "maximum usage", "sabse zyada", "kab use hui", "सबसे ज़्यादा", "सबसे ज्यादा", "ਸਭ ਤੋਂ ਵੱਧ")):
            return "peak"
        if any(x in text for x in ("yesterday", "last day", "kal ki", "kal ka", "kal consumption", "कल", "ਕੱਲ੍ਹ", "ਪਿਛਲੇ ਦਿਨ")):
            return "daily"
        if any(x in text for x in ("total consumption", "total energy", "overall consumption", "कुल खपत", "ਕੁੱਲ ਖਪਤ")):
            return "total"
        if any(x in text for x in ("consume", "consumption", "usage", "electricity", "energy", "how much", "खपत", "बिजली", "ਵਰਤੋਂ", "ਬਿਜਲੀ")):
            return "consumption"
        return "help"

    intent = match(q)
    # An explicit current intent wins; use prior wording only when the user gives a short follow-up.
    if intent != "help":
        return intent, q
    if follow_up and previous_question:
        combined = f"{_normal(previous_question)} {q}".strip()
        return match(combined), combined
    return "help", q


def _kwh(record) -> float:
    return record.value / 1000 if record.unit.lower() == "wh" else record.value


def answer_question(question: str, previous_question: str, language: str, building, records, data: dict, tariff: float | None, recommendations: dict) -> tuple[str, str]:
    intent, query = classify_intent(question, previous_question)
    lang = language if language in LANGUAGES else "en-IN"
    name = building.name
    values = [_kwh(r) for r in records]
    latest = data["metrics"]["latest"]
    recent = data["metrics"]["last_24h"]
    day = records[-1].timestamp.date()
    if intent == "simulation":
        percentage_match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*(?:%|percent\b|per cent\b|प्रतिशत)", _normal(question)) or re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*(?:%|percent\b|per cent\b|प्रतिशत)", query)
        if not percentage_match:
            phrases = {
                "en-IN": "Tell me the reduction percentage (for example, 10%) and I can calculate a clearly labelled scenario.",
                "hi-IN": "कृपया कमी का प्रतिशत बताएं (उदाहरण: 10%), फिर मैं एक अनुमानित परिदृश्य निकाल दूंगा।",
                "hi-en": "Reduction percentage batayein (jaise 10%), phir main ek hypothetical scenario calculate kar dunga.",
                "pa-IN": "ਕਮੀ ਦਾ ਪ੍ਰਤੀਸ਼ਤ ਦੱਸੋ (ਜਿਵੇਂ 10%), ਫਿਰ ਮੈਂ ਇੱਕ ਅਨੁਮਾਨੀ ਦ੍ਰਿਸ਼ ਦੀ ਗਣਨਾ ਕਰਾਂਗਾ।",
            }
            return "simulation", phrases[lang]
        pct = min(100.0, max(0.0, float(percentage_match.group(1))))
        saved = recent * pct / 100
        after = recent - saved
        cost_saving = saved * tariff if tariff and tariff > 0 else None
        templates = {
            "en-IN": f"Hypothetical scenario for {name}: applying a uniform {pct:g}% reduction to the latest imported 24-hour use of {recent:,.3f} kWh would mean {saved:,.3f} kWh assumed savings and {after:,.3f} kWh remaining. This is an assumption, not a measured or guaranteed saving." + (f" At the supplied tariff, the scenario cost reduction is ₹{cost_saving:,.2f}." if cost_saving is not None else " Cost savings are unavailable because no tariff was supplied."),
            "hi-IN": f"{name} का काल्पनिक परिदृश्य: सबसे हाल की आयातित 24 घंटे की खपत {recent:,.3f} kWh पर समान {pct:g}% कमी मानने से {saved:,.3f} kWh की अनुमानित बचत और {after:,.3f} kWh शेष खपत होगी। यह धारणा है, मापी गई या गारंटीकृत बचत नहीं।" + (f" दिए गए टैरिफ पर लागत में अनुमानित कमी ₹{cost_saving:,.2f} है।" if cost_saving is not None else " टैरिफ न होने से लागत की बचत उपलब्ध नहीं है।"),
            "hi-en": f"{name} ka hypothetical scenario: latest imported 24-hour use {recent:,.3f} kWh par uniform {pct:g}% reduction maan kar {saved:,.3f} kWh assumed saving aur {after:,.3f} kWh remaining hoga. Yeh assumption hai, measured ya guaranteed saving nahi." + (f" Diye gaye tariff par estimated cost reduction ₹{cost_saving:,.2f} hai." if cost_saving is not None else " Tariff nahi diya gaya, isliye cost saving available nahi hai."),
            "pa-IN": f"{name} ਲਈ ਕਾਲਪਨਿਕ ਦ੍ਰਿਸ਼: ਨਵੀਨਤਮ ਆਯਾਤ ਕੀਤੀ 24 ਘੰਟਿਆਂ ਦੀ ਖਪਤ {recent:,.3f} kWh 'ਤੇ ਇੱਕਸਾਰ {pct:g}% ਕਮੀ ਮੰਨਣ ਨਾਲ {saved:,.3f} kWh ਅਨੁਮਾਨਿਤ ਬਚਤ ਅਤੇ {after:,.3f} kWh ਬਾਕੀ ਖਪਤ ਹੋਵੇਗੀ। ਇਹ ਧਾਰਨਾ ਹੈ, ਮਾਪੀ ਜਾਂ ਗਾਰੰਟੀਸ਼ੁਦਾ ਬਚਤ ਨਹੀਂ।" + (f" ਦਿੱਤੇ ਟੈਰਿਫ ਅਨੁਸਾਰ ਲਾਗਤ ਵਿੱਚ ਅਨੁਮਾਨਿਤ ਕਮੀ ₹{cost_saving:,.2f} ਹੈ।" if cost_saving is not None else " ਟੈਰਿਫ ਨਾ ਹੋਣ ਕਰਕੇ ਲਾਗਤ ਦੀ ਬਚਤ ਉਪਲਬਧ ਨਹੀਂ ਹੈ।"),
        }
        return intent, templates[lang]

    if intent == "recommendation":
        if not recommendations.get("available") or not recommendations.get("items"):
            texts = {"en-IN": recommendations.get("message", "There is not enough data for a reliable recommendation."), "hi-IN": "विश्वसनीय सुझाव देने के लिए पर्याप्त मीटर डेटा उपलब्ध नहीं है।", "hi-en": "Reliable recommendation ke liye abhi paryapt meter data nahi hai.", "pa-IN": "ਭਰੋਸੇਯੋਗ ਸਿਫ਼ਾਰਸ਼ ਲਈ ਕਾਫ਼ੀ ਮੀਟਰ ਡਾਟਾ ਉਪਲਬਧ ਨਹੀਂ ਹੈ।"}
            return intent, texts[lang]
        item = recommendations["items"][0]
        hour = item["evidence"]["peak_hour"]
        mean = item["evidence"]["average_at_peak"]
        texts = {
            "en-IN": f"For {name}, the measured hourly pattern averages highest around {hour:02d}:00 ({mean:g} kWh per record). Review schedules, occupancy and equipment at that time. Whole-building data cannot identify the end use or prove savings.",
            "hi-IN": f"{name} में मापे गए प्रति-घंटे के पैटर्न का औसत लगभग {hour:02d}:00 बजे सबसे अधिक है ({mean:g} kWh प्रति रीडिंग)। उस समय के संचालन, उपस्थिति और उपकरणों की समीक्षा करें। पूरे भवन का डेटा उपयोग का कारण या बचत सिद्ध नहीं करता।",
            "hi-en": f"{name} mein metered hourly pattern ka average {hour:02d}:00 ke aas-paas sabse zyada hai ({mean:g} kWh per record). Us waqt schedule, occupancy aur equipment review karein. Whole-building data se end-use ya saving prove nahi hoti.",
            "pa-IN": f"{name} ਵਿੱਚ ਮਾਪੇ ਗਏ ਘੰਟਾਵਾਰ ਪੈਟਰਨ ਦਾ ਔਸਤ ਲਗਭਗ {hour:02d}:00 ਵਜੇ ਸਭ ਤੋਂ ਵੱਧ ਹੈ ({mean:g} kWh ਪ੍ਰਤੀ ਰੀਡਿੰਗ)। ਉਸ ਵੇਲੇ ਦੇ ਸ਼ਡਿਊਲ, ਮੌਜੂਦਗੀ ਅਤੇ ਉਪਕਰਣਾਂ ਦੀ ਸਮੀਖਿਆ ਕਰੋ। ਪੂਰੀ ਇਮਾਰਤ ਦਾ ਡਾਟਾ ਵਰਤੋਂ ਦਾ ਕਾਰਨ ਜਾਂ ਬਚਤ ਸਾਬਤ ਨਹੀਂ ਕਰਦਾ।",
        }
        return intent, texts[lang]

    if intent == "hourly_average":
        by_hour: dict[int, list[float]] = {}
        for record, value in zip(records, values):
            by_hour.setdefault(record.timestamp.hour, []).append(value)
        if not by_hour:
            return intent, "There are no hourly readings to compare."
        hour = max(by_hour, key=lambda h: sum(by_hour[h]) / len(by_hour[h]))
        average = sum(by_hour[hour]) / len(by_hour[hour])
        n = len(by_hour[hour])
        texts = {
            "en-IN": f"Across {len(records):,} imported readings for {name}, the highest average time-of-day is {hour:02d}:00–{(hour + 1) % 24:02d}:00: {average:,.3f} kWh per record across {n:,} readings. This groups records by their stored timestamp hour.",
            "hi-IN": f"{name} की {len(records):,} आयातित रीडिंग में दिन के समय का सबसे अधिक औसत {hour:02d}:00–{(hour + 1) % 24:02d}:00 है: {average:,.3f} kWh प्रति रीडिंग ({n:,} रीडिंग)। यह संग्रहित टाइमस्टैम्प के घंटे के आधार पर गणना है।",
            "hi-en": f"{name} ki {len(records):,} imported readings mein time-of-day ka highest average {hour:02d}:00–{(hour + 1) % 24:02d}:00 hai: {average:,.3f} kWh per record ({n:,} readings). Yeh stored timestamp ke hour se group kiya gaya hai.",
            "pa-IN": f"{name} ਦੀਆਂ {len(records):,} ਆਯਾਤ ਕੀਤੀਆਂ ਰੀਡਿੰਗਾਂ ਵਿੱਚ ਦਿਨ ਦੇ ਸਮੇਂ ਦਾ ਸਭ ਤੋਂ ਵੱਧ ਔਸਤ {hour:02d}:00–{(hour + 1) % 24:02d}:00 ਹੈ: {average:,.3f} kWh ਪ੍ਰਤੀ ਰੀਡਿੰਗ ({n:,} ਰੀਡਿੰਗਾਂ)। ਇਹ ਸੰਭਾਲੇ ਟਾਈਮਸਟੈਂਪ ਦੇ ਘੰਟੇ ਅਨੁਸਾਰ ਗਿਣਤੀ ਹੈ।",
        }
        return intent, texts[lang]

    if intent == "peak":
        i = max(range(len(values)), key=values.__getitem__)
        record = records[i]
        stamp = record.timestamp.strftime("%Y-%m-%d %H:%M")
        templates = {
            "en-IN": f"The largest individual meter reading in {name}'s imported data is {values[i]:,.3f} kWh at {stamp} (stored timestamp). This is a peak reading, not a daily total.",
            "hi-IN": f"{name} के आयातित डेटा में सबसे बड़ी एकल मीटर रीडिंग {stamp} (संग्रहित टाइमस्टैम्प) पर {values[i]:,.3f} kWh है। यह अधिकतम रीडिंग है, दैनिक कुल नहीं।",
            "hi-en": f"{name} ke imported data mein sabse badi individual meter reading {stamp} (stored timestamp) par {values[i]:,.3f} kWh hai. Yeh peak reading hai, daily total nahi.",
            "pa-IN": f"{name} ਦੇ ਆਯਾਤ ਕੀਤੇ ਡਾਟਾ ਵਿੱਚ ਸਭ ਤੋਂ ਵੱਡੀ ਇਕੱਲੀ ਮੀਟਰ ਰੀਡਿੰਗ {stamp} (ਸੰਭਾਲਿਆ ਟਾਈਮਸਟੈਂਪ) 'ਤੇ {values[i]:,.3f} kWh ਹੈ। ਇਹ ਚੋਟੀ ਦੀ ਰੀਡਿੰਗ ਹੈ, ਰੋਜ਼ਾਨਾ ਕੁੱਲ ਨਹੀਂ।",
        }
        return intent, templates[lang]

    if intent == "daily":
        date = day - timedelta(days=1)
        day_values = [_kwh(r) for r in records if r.timestamp.date() == date]
        if not day_values:
            texts = {"en-IN": f"No readings were imported for {date.isoformat()} relative to the latest stored date ({day.isoformat()}).", "hi-IN": f"नवीनतम संग्रहित तारीख ({day.isoformat()}) से पिछले दिन {date.isoformat()} के लिए कोई रीडिंग आयात नहीं हुई।", "hi-en": f"Latest stored date ({day.isoformat()}) se pichhle din {date.isoformat()} ke liye koi reading import nahi hui.", "pa-IN": f"ਨਵੀਨਤਮ ਸੰਭਾਲੀ ਤਾਰੀਖ ({day.isoformat()}) ਤੋਂ ਪਿਛਲੇ ਦਿਨ {date.isoformat()} ਲਈ ਕੋਈ ਰੀਡਿੰਗ ਆਯਾਤ ਨਹੀਂ ਹੋਈ।"}
            return intent, texts[lang]
        value = sum(day_values)
        templates = {
            "en-IN": f"On the calendar day before the latest stored date ({date.isoformat()}), {name} recorded {value:,.3f} kWh across {len(day_values):,} readings.",
            "hi-IN": f"नवीनतम संग्रहित तारीख से पहले वाले दिन ({date.isoformat()}), {name} में {len(day_values):,} रीडिंग के साथ {value:,.3f} kWh दर्ज हुआ।",
            "hi-en": f"Latest stored date se pichhle calendar day ({date.isoformat()}) par {name} ne {len(day_values):,} readings mein {value:,.3f} kWh record kiya.",
            "pa-IN": f"ਨਵੀਨਤਮ ਸੰਭਾਲੀ ਤਾਰੀਖ ਤੋਂ ਪਿਛਲੇ ਕੈਲੰਡਰ ਦਿਨ ({date.isoformat()}), {name} ਨੇ {len(day_values):,} ਰੀਡਿੰਗਾਂ ਵਿੱਚ {value:,.3f} kWh ਦਰਜ ਕੀਤਾ।",
        }
        return intent, templates[lang]

    if intent == "total":
        total = sum(values)
        templates = {"en-IN": f"{name} has {total:,.3f} kWh across {len(records):,} imported meter readings, covering {records[0].timestamp:%Y-%m-%d} through {records[-1].timestamp:%Y-%m-%d}. This total reflects the imported dataset only.", "hi-IN": f"{name} में {len(records):,} आयातित मीटर रीडिंग का कुल {total:,.3f} kWh है। डेटा {records[0].timestamp:%Y-%m-%d} से {records[-1].timestamp:%Y-%m-%d} तक है; यह केवल आयातित डेटा का कुल है।", "hi-en": f"{name} ke {len(records):,} imported meter readings ka total {total:,.3f} kWh hai. Coverage {records[0].timestamp:%Y-%m-%d} se {records[-1].timestamp:%Y-%m-%d} tak hai; yeh sirf imported data ka total hai.", "pa-IN": f"{name} ਦੀਆਂ {len(records):,} ਆਯਾਤ ਕੀਤੀਆਂ ਮੀਟਰ ਰੀਡਿੰਗਾਂ ਦਾ ਕੁੱਲ {total:,.3f} kWh ਹੈ। ਡਾਟਾ {records[0].timestamp:%Y-%m-%d} ਤੋਂ {records[-1].timestamp:%Y-%m-%d} ਤੱਕ ਹੈ; ਇਹ ਸਿਰਫ਼ ਆਯਾਤ ਕੀਤੇ ਡਾਟੇ ਦਾ ਕੁੱਲ ਹੈ।"}
        return intent, templates[lang]

    if intent == "forecast":
        f = data["forecast"]
        if not f.get("available"):
            reason=f.get('reason', 'insufficient data')
            texts={"en-IN":f"A forecast is unavailable for {name}: {reason}","hi-IN":f"{name} के लिए पूर्वानुमान उपलब्ध नहीं है: {reason}","hi-en":f"{name} ke liye forecast available nahi hai: {reason}","pa-IN":f"{name} ਲਈ ਪੂਰਵ-ਅਨੁਮਾਨ ਉਪਲਬਧ ਨਹੀਂ ਹੈ: {reason}"}
            return intent, texts[lang]
        interval_hours = f.get("sampling_interval_seconds", 3600) / 3600
        points = f.get("points", [])
        forecast_total = sum(x["value"] for x in points)
        coverage_hours = len(points) * interval_hours
        templates={"en-IN":f"The Random Forest forecast for {name} provides {len(points)} future records at about {interval_hours:g}-hour intervals (approximately {coverage_hours:g} hours of model horizon), totalling {forecast_total:,.3f} kWh. Held-out MAE is {f['metrics']['mae']} kWh per record; this is a model estimate, not a guarantee.","hi-IN":f"{name} के लिए Random Forest पूर्वानुमान लगभग {interval_hours:g}-घंटे के अंतराल पर {len(points)} भविष्य रीडिंग देता है (लगभग {coverage_hours:g} घंटे), कुल {forecast_total:,.3f} kWh। परीक्षण डेटा पर MAE {f['metrics']['mae']} kWh प्रति रीडिंग है; यह मॉडल अनुमान है, गारंटी नहीं।","hi-en":f"{name} ke liye Random Forest forecast lagbhag {interval_hours:g}-hour intervals par {len(points)} future readings deta hai (karib {coverage_hours:g} hours), total {forecast_total:,.3f} kWh. Held-out MAE {f['metrics']['mae']} kWh per record hai; yeh model estimate hai, guarantee nahi.","pa-IN":f"{name} ਲਈ Random Forest ਪੂਰਵ-ਅਨੁਮਾਨ ਲਗਭਗ {interval_hours:g}-ਘੰਟੇ ਦੇ ਅੰਤਰਾਲ 'ਤੇ {len(points)} ਭਵਿੱਖੀ ਰੀਡਿੰਗਾਂ ਦਿੰਦਾ ਹੈ (ਕਰੀਬ {coverage_hours:g} ਘੰਟੇ), ਕੁੱਲ {forecast_total:,.3f} kWh। ਟੈਸਟ ਡਾਟੇ 'ਤੇ MAE {f['metrics']['mae']} kWh ਪ੍ਰਤੀ ਰੀਡਿੰਗ ਹੈ; ਇਹ ਮਾਡਲ ਅਨੁਮਾਨ ਹੈ, ਗਾਰੰਟੀ ਨਹੀਂ।"}
        return intent, templates[lang]

    if intent == "anomaly":
        flags = data.get("anomalies", [])
        templates={"en-IN":(f"I found {len(flags)} recent statistical deviation flags for {name}. They identify readings to review; they do not prove waste or a fault." if flags else f"No recent readings in {name} crossed the current rolling statistical threshold. This does not rule out operational issues."),"hi-IN":(f"{name} में हाल की {len(flags)} सांख्यिकीय विचलन रीडिंग समीक्षा के लिए मिलीं। वे बर्बादी या खराबी साबित नहीं करतीं।" if flags else f"{name} की हाल की कोई रीडिंग वर्तमान सांख्यिकीय सीमा से बाहर नहीं गई। इससे समस्या की संभावना समाप्त नहीं होती।"),"hi-en":(f"{name} mein {len(flags)} recent statistical deviation flags mile hain. In readings ko review karein; yeh waste ya fault prove nahi karte." if flags else f"{name} ki recent readings current rolling statistical threshold se bahar nahi gayi. Isse operational issue ki sambhavna kharij nahi hoti."),"pa-IN":(f"{name} ਵਿੱਚ ਹਾਲੀਆ {len(flags)} ਅੰਕੜਾ-ਅਧਾਰਿਤ ਤਬਦੀਲੀ ਸੰਕੇਤ ਮਿਲੇ ਹਨ। ਇਹ ਸਮੀਖਿਆ ਲਈ ਹਨ; ਬਰਬਾਦੀ ਜਾਂ ਖਰਾਬੀ ਸਾਬਤ ਨਹੀਂ ਕਰਦੇ।" if flags else f"{name} ਦੀ ਕੋਈ ਹਾਲੀਆ ਰੀਡਿੰਗ ਮੌਜੂਦਾ ਅੰਕੜਾ ਸੀਮਾ ਤੋਂ ਬਾਹਰ ਨਹੀਂ ਗਈ। ਇਸ ਨਾਲ ਕਾਰਜਕਾਰੀ ਸਮੱਸਿਆ ਦੀ ਸੰਭਾਵਨਾ ਖਤਮ ਨਹੀਂ ਹੁੰਦੀ।")}
        return intent, templates[lang]

    if intent == "cost":
        if not tariff or tariff <= 0:
            texts = {"en-IN": "Estimated electricity cost is unavailable because no tariff was supplied. Enter a rate in the dashboard to calculate it from measured use.", "hi-IN": "अनुमानित बिजली लागत उपलब्ध नहीं है क्योंकि टैरिफ नहीं दिया गया। मापी गई खपत से लागत निकालने के लिए डैशबोर्ड में दर दर्ज करें।", "hi-en": "Tariff nahi diya gaya, isliye estimated electricity cost available nahi hai. Measured use se calculate karne ke liye dashboard mein rate enter karein.", "pa-IN": "ਟੈਰਿਫ ਨਾ ਦਿੱਤੇ ਜਾਣ ਕਰਕੇ ਅਨੁਮਾਨਿਤ ਬਿਜਲੀ ਲਾਗਤ ਉਪਲਬਧ ਨਹੀਂ ਹੈ। ਮਾਪੀ ਖਪਤ ਤੋਂ ਲਾਗਤ ਕੱਢਣ ਲਈ ਡੈਸ਼ਬੋਰਡ ਵਿੱਚ ਦਰ ਭਰੋ।"}
            return intent, texts[lang]
        amount = recent * tariff
        templates={"en-IN":f"Using the supplied tariff of ₹{tariff:g}/kWh, the estimated cost for the latest imported 24-hour window ({recent:,.3f} kWh) is ₹{amount:,.2f}. This is an estimate and may exclude taxes, demand charges and time-of-use rates.","hi-IN":f"दिए गए ₹{tariff:g}/kWh टैरिफ से सबसे हाल की आयातित 24 घंटे की खपत ({recent:,.3f} kWh) की अनुमानित लागत ₹{amount:,.2f} है। इसमें कर, डिमांड शुल्क और समय-आधारित दरें शामिल नहीं हो सकतीं।","hi-en":f"Diye gaye ₹{tariff:g}/kWh tariff par latest imported 24-hour use ({recent:,.3f} kWh) ki estimated cost ₹{amount:,.2f} hai. Taxes, demand charges aur time-of-use rates ismein shamil na hon.","pa-IN":f"ਦਿੱਤੇ ₹{tariff:g}/kWh ਟੈਰਿਫ ਨਾਲ ਨਵੀਨਤਮ ਆਯਾਤ ਕੀਤੀ 24 ਘੰਟਿਆਂ ਦੀ ਖਪਤ ({recent:,.3f} kWh) ਦੀ ਅਨੁਮਾਨਿਤ ਲਾਗਤ ₹{amount:,.2f} ਹੈ। ਇਸ ਵਿੱਚ ਟੈਕਸ, ਡਿਮਾਂਡ ਚਾਰਜ ਅਤੇ ਸਮਾਂ-ਅਧਾਰਿਤ ਦਰਾਂ ਸ਼ਾਮਲ ਨਾ ਹੋ ਸਕਦੀਆਂ ਹਨ।"}
        return intent, templates[lang]

    if intent == "comparison":
        previous = data["metrics"].get("previous_24h")
        if previous is None:
            return intent, "A previous 24-hour comparison window is not present in the imported readings."
        change = data["metrics"].get("change_pct")
        change_text = "change unavailable" if change is None else f"{abs(change):g}% {'higher' if change > 0 else 'lower' if change < 0 else 'unchanged'}"
        templates={"en-IN":f"For {name}, the latest imported 24-hour window totals {recent:,.3f} kWh; the preceding 24-hour window totals {previous:,.3f} kWh, a {change_text} change. The windows are relative to the latest stored meter timestamp.","hi-IN":f"{name} की नवीनतम आयातित 24 घंटे की खपत {recent:,.3f} kWh है; पिछली 24 घंटे की अवधि {previous:,.3f} kWh थी, यानी {change_text} बदलाव। अवधियां नवीनतम संग्रहित टाइमस्टैम्प से तय होती हैं।","hi-en":f"{name} ka latest imported 24-hour total {recent:,.3f} kWh hai; usse pehle ke 24 hours ka total {previous:,.3f} kWh tha, yani {change_text} change. Dono windows latest stored meter timestamp ke hisab se hain.","pa-IN":f"{name} ਦੀ ਨਵੀਨਤਮ ਆਯਾਤ ਕੀਤੀ 24 ਘੰਟਿਆਂ ਦੀ ਖਪਤ {recent:,.3f} kWh ਹੈ; ਪਿਛਲੇ 24 ਘੰਟਿਆਂ ਦੀ ਖਪਤ {previous:,.3f} kWh ਸੀ, ਅਰਥਾਤ {change_text} ਤਬਦੀਲੀ। ਮਿਆਦਾਂ ਨਵੀਨਤਮ ਸੰਭਾਲੇ ਟਾਈਮਸਟੈਂਪ ਤੋਂ ਗਿਣੀਆਂ ਹਨ।"}
        return intent, templates[lang]

    if intent == "consumption":
        templates={"en-IN":f"The latest reading for {name} is {latest:,.3f} kWh per record. The latest imported 24-hour window totals {recent:,.3f} kWh across its meter readings. Data coverage is {data['coverage']['from']} through {data['coverage']['to']} (stored timestamps).","hi-IN":f"{name} की नवीनतम रीडिंग {latest:,.3f} kWh प्रति रिकॉर्ड है। सबसे हाल की आयातित 24 घंटे की अवधि में कुल खपत {recent:,.3f} kWh है। डेटा कवरेज {data['coverage']['from']} से {data['coverage']['to']} तक है।","hi-en":f"{name} ki latest reading {latest:,.3f} kWh per record hai. Latest imported 24-hour window ka total {recent:,.3f} kWh hai. Data coverage {data['coverage']['from']} se {data['coverage']['to']} tak hai.","pa-IN":f"{name} ਦੀ ਨਵੀਨਤਮ ਰੀਡਿੰਗ {latest:,.3f} kWh ਪ੍ਰਤੀ ਰਿਕਾਰਡ ਹੈ। ਨਵੀਨਤਮ ਆਯਾਤ ਕੀਤੀ 24 ਘੰਟਿਆਂ ਦੀ ਖਪਤ {recent:,.3f} kWh ਹੈ। ਡਾਟਾ ਕਵਰੇਜ {data['coverage']['from']} ਤੋਂ {data['coverage']['to']} ਤੱਕ ਹੈ।"}
        return intent, templates[lang]

    help_text = {
        "en-IN": "I can answer about imported consumption, peak readings, hourly averages, yesterday's total, forecasts, statistical anomalies, tariff-based cost, recommendations, or a hypothetical reduction scenario. Which would you like?",
        "hi-IN": "मैं आयातित खपत, अधिकतम रीडिंग, प्रति-घंटे औसत, पिछले दिन का कुल, पूर्वानुमान, सांख्यिकीय असामान्यताएं, टैरिफ-आधारित लागत, सुझाव या काल्पनिक कमी के परिदृश्य पर उत्तर दे सकता हूं।",
        "hi-en": "Main imported consumption, peak reading, hourly average, pichhle din ka total, forecast, anomaly flags, tariff-based cost, recommendation ya hypothetical reduction scenario ke baare mein jawab de sakta hoon.",
        "pa-IN": "ਮੈਂ ਆਯਾਤ ਕੀਤੀ ਖਪਤ, ਚੋਟੀ ਦੀ ਰੀਡਿੰਗ, ਘੰਟਾਵਾਰ ਔਸਤ, ਪਿਛਲੇ ਦਿਨ ਦਾ ਕੁੱਲ, ਪੂਰਵ-ਅਨੁਮਾਨ, ਅਸਧਾਰਨ ਰੀਡਿੰਗਾਂ, ਟੈਰਿਫ ਅਧਾਰਿਤ ਲਾਗਤ, ਸਿਫ਼ਾਰਸ਼ਾਂ ਜਾਂ ਕਾਲਪਨਿਕ ਕਮੀ ਦੇ ਦ੍ਰਿਸ਼ ਬਾਰੇ ਜਵਾਬ ਦੇ ਸਕਦਾ ਹਾਂ।",
    }
    return intent, help_text[lang]
