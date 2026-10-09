"""Retain every real model attempt, distinguishing failed unknown usage from reported tokens."""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import httpx
from openai import APIConnectionError
from langchain_core.messages import AIMessage, HumanMessage
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops import llm

attempts=[]
class Model:
    def invoke(self, messages, config):
        attempts.append(config)
        if len(attempts)==1:
            raise APIConnectionError(request=httpx.Request('POST','https://sample.test'))
        return AIMessage(content='{}',usage_metadata={'input_tokens':10,'output_tokens':5,'total_tokens':15})

with tempfile.TemporaryDirectory() as temp, patch.object(llm,'chat_model',Model):
    directory=Path(temp)
    token=llm.CAPTURE.set(directory)
    try:
        assert llm.invoke(lambda model:model,[HumanMessage('public')],'test').text=='{}'
    finally:
        llm.CAPTURE.reset(token)
    records=sorted((json.loads(p.read_text()) for p in directory.glob('*.json')),key=lambda v:v['attempt'])
    assert len(records)==2 and records[0]['status']=='failed' and 'usage' not in records[0]
    assert records[1]['usage']['total_tokens']==15 and all(r['elapsed_seconds']>=0 for r in records)
    assert llm.CAPTURE.get() is None
print('model accounting: transient attempts, unknown failure usage, reported tokens and context reset passed')
