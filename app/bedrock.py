"""Call insights on Amazon Bedrock (Amazon Nova Micro via the Converse API).

GET /api/insights/{agent} reads the agent's most recent records and asks the model for a short operator
brief: top caller intents, missed opportunities, and the next actions. Enabled only when BEDROCK_MODEL_ID
is set (the AWS deployment sets it); capped per day by INSIGHTS_DAILY_CAP so traffic can't run up a bill."""
import datetime as _dt
import json
import os

_CALLS: dict[str, int] = {}


def enabled() -> bool:
    return bool(os.getenv("BEDROCK_MODEL_ID"))


def _budget_ok() -> bool:
    day = _dt.datetime.utcnow().strftime("%Y-%m-%d")
    n = _CALLS.get(day, 0)
    if n >= int(os.getenv("INSIGHTS_DAILY_CAP", "100")):
        return False
    _CALLS.clear(); _CALLS[day] = n + 1
    return True


def insights(agent_name: str, records: list[dict]) -> dict:
    if not enabled():
        return {"error": "Bedrock not configured (set BEDROCK_MODEL_ID)"}
    if not records:
        return {"agent": agent_name, "brief": "No calls captured yet.", "model": os.getenv("BEDROCK_MODEL_ID")}
    if not _budget_ok():
        return {"agent": agent_name, "brief": "Daily insights limit reached; try again tomorrow.", "capped": True}
    import boto3  # bundled in the Lambda runtime
    rows = [{k: r.get(k) for k in ("name", "intent", "outcome", "appointment", "summary")} for r in records[:20]]
    prompt = (f"You are an operations analyst for '{agent_name}', an AI phone agent. Here are its most recent call "
              f"records as JSON:\n{json.dumps(rows, default=str)}\n\nWrite a brief for the business owner with three "
              "short sections: Top intents (with counts), Missed opportunities, Next actions. Use only these records; "
              "under 120 words.")
    from botocore.exceptions import BotoCoreError, ClientError
    client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
    try:
        resp = client.converse(modelId=os.environ["BEDROCK_MODEL_ID"],
                               messages=[{"role": "user", "content": [{"text": prompt}]}],
                               inferenceConfig={"maxTokens": 300, "temperature": 0.2})
    except (ClientError, BotoCoreError) as e:   # throttling, access, verification: a clear 503, never a raw 500
        code = getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)
        return {"error": f"Bedrock unavailable ({code}). Try again later.", "agent": agent_name}
    text = resp["output"]["message"]["content"][0]["text"]
    return {"agent": agent_name, "brief": text, "model": os.environ["BEDROCK_MODEL_ID"],
            "usage": resp.get("usage", {}), "records_used": len(rows)}
