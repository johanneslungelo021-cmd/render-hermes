#!/usr/bin/env bash
# run_numerai.sh — Full Numerai pipeline: predict → submit → verify
set -e
cd /root/the-hidden-ledger

echo "============================================"
echo " Numerai Pipeline"
echo "============================================"

# Step 1: Generate ensemble predictions
echo ""
echo "[1/3] Generating ensemble predictions..."
python3 ledger/numerai_model.py --predict

# Step 2: Submit
echo ""
echo "[2/3] Submitting predictions..."
python3 ledger/numerai_pipeline.py --upload data/numerai_submission.csv

# Step 3: Verify
echo ""
echo "[3/3] Latest submissions:"
python3 -c "
import json, os, urllib.request
API_URL = 'https://api-tournament.numer.ai/'
API_KEY = os.getenv('NUMERAI_API_KEY', '')
query = '''query(\$mid: String!) { submissions(modelId: \$mid) { id filename status selected round { number } } }'''
payload = {'query': query, 'variables': {'mid': os.getenv('NUMERAI_MODEL_ID', '')}}
req = urllib.request.Request(API_URL, data=json.dumps(payload).encode(), headers={'Content-Type':'application/json','Authorization':f'Token {API_KEY}','Accept':'application/json','User-Agent':'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=15) as r:
    for s in json.loads(r.read().decode()).get('data',{}).get('submissions',[]):
        print(f\"  {'✅' if s['selected'] else '  '} Round {s['round']['number']} — {s['id'][:8]}... ({s['filename']})\")
"
echo ""
echo "✅ Done!"
