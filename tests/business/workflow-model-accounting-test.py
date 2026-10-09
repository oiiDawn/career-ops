"""Retain every real model attempt, distinguishing failed unknown usage from reported tokens."""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from types import SimpleNamespace
import httpx
from openai import APIConnectionError
from langchain_core.messages import AIMessage, HumanMessage
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops import llm

attempts=[]
reported_failure=False
class Model:
    def invoke(self, messages, config):
        attempts.append(config)
        if len(attempts)==1:
            error=APIConnectionError(request=httpx.Request('POST','https://sample.test'))
            if reported_failure:
                error.completion=SimpleNamespace(usage=SimpleNamespace(prompt_tokens=7,completion_tokens=3,total_tokens=10))
            raise error
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
    attempts.clear()
    reported_failure=True
    token=llm.CAPTURE.set(directory)
    try:
        llm.invoke(lambda model:model,[HumanMessage('public')],'known-failure')
    finally:
        llm.CAPTURE.reset(token)
    failures=[json.loads(p.read_text()) for p in directory.glob('*.json') if json.loads(p.read_text())['name']=='known-failure' and json.loads(p.read_text())['status']=='failed']
    assert len(failures)==1 and failures[0]['usage']['total_tokens']==10
print('model accounting: transient attempts, unknown failure usage, reported tokens and context reset passed')
