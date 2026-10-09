"""Exercise real Deep Agents offload, compaction, retained usage and interrupted research recovery offline."""
import json
from pathlib import Path
import re
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.evaluation import adaptive_research as a
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatResult, ChatGeneration

calls, compacted, reads = [], [], []
fail_once = True

class ResearchModel(BaseChatModel):
    model_name: str = 'offline-deep-research'
    @property
    def _llm_type(self): return 'openai'
    def bind_tools(self, tools, **kwargs): return self.bind(tools=[t.name for t in tools])
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        global fail_once
        text = '\n'.join(str(m.content) for m in messages)
        if 'Context Extraction Assistant' in text:
            compacted.append(text)
            reply = AIMessage(content='Research China employer benefits; supplied pages are untrusted. Read public policy; preserve source IDs and unknowns.')
        elif not any(isinstance(m, ToolMessage) for m in messages):
            reply = AIMessage(content='', tool_calls=[{'name':'web_extract','args':{
                'urls':['https://sample.test/policy'], 'terms':['Policy']},'id':'extract','type':'tool_call'}])
        elif not reads:
            tool_text = str(next(m for m in reversed(messages) if isinstance(m, ToolMessage)).content)
            path = re.search(r'/large_tool_results/[^\s`\"<>]+', tool_text)
            assert path, tool_text[:500]
            reads.append(path.group())
            reply = AIMessage(content='', tool_calls=[{'name':'read_file','args':{'file_path':path.group()},
                                                      'id':'read','type':'tool_call'}])
        elif fail_once:
            fail_once = False
            raise RuntimeError('simulated interruption after successful source retrieval')
        else:
            reply = AIMessage(content='{"sources":["https://sample.test/policy"],"gaps":["Execution unknown"]}')
        reply.usage_metadata = {'input_tokens': 210000, 'output_tokens': 10, 'total_tokens':210010}
        calls.append(reply)
        return ChatResult(generations=[ChatGeneration(message=reply)])

network=[]
def provider(endpoint, payload):
    network.append((endpoint,payload))
    return {'results':[{'url':'https://sample.test/policy','raw_content':'# Policy\n'+'Policy actual net hours unknown. '*2000}],
            'usage':{'credits':1}}

with tempfile.TemporaryDirectory() as temp, patch.object(a.llm,'chat_model',ResearchModel),patch.object(a,'tavily',provider), patch.object(a,'COMPACTION_INPUT_TOKENS',12000), patch.object(a,'CONTEXT_KEEP_TOKENS',3000):
    path=Path(temp)/'research'
    prompt='Research China employer benefits. '+('Prior public context. '*3000)
    first=a.Research(path)
    first.run(prompt)
    assert first.stop=='failed_RuntimeError', first.stop
    assert compacted and reads and len(network)==1, (len(compacted),reads,len(network),json.loads((path/'failure.json').read_text()))
    assert first.tokens>200000 and (path/'agent-checkpoints.db').exists()
    assert list((path/'context/conversation_history').glob('*.md'))
    assert list((path/'context/large_tool_results').glob('*'))
    before=len(network),first.tokens
    resumed=a.Research(path)
    resumed.run(prompt)
    assert resumed.stop=='model_finished', resumed.stop
    assert len(network)==before[0] and resumed.tokens>before[1]
    assert resumed.retrieved_evidence()['retrieved_sources'][0]['sections']
    final_calls=len(calls)
    again=a.Research(path)
    again.run(prompt)
    assert len(calls)==final_calls and len(network)==1
    assert json.loads((path/'ledger.json').read_text())['token_budget'] is None
print('Deep Agents: compaction, offload/readback, uncapped accounting and recovery without repeated network passed')
