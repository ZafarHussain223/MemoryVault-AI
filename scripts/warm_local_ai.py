"""Warm the already-running local service without using private source material."""
from local_ai_runtime import Service,CHAT_MODEL,EMBED_MODEL
service=Service(11434)
print('Checking local Ollama...',flush=True);print(service.api('/api/version',timeout=5))
service.api('/api/embed',{'model':EMBED_MODEL,'input':['Local model readiness check.'],'dimensions':384,'keep_alive':'300s','options':{'num_ctx':4096,'num_batch':128}})
print('Embedding model is ready.',flush=True)
result=service.api('/api/chat',{'model':CHAT_MODEL,'messages':[{'role':'user','content':'Reply with the word ready.'}],'stream':False,'keep_alive':'300s','options':{'num_ctx':8192,'num_predict':8,'num_batch':128,'temperature':.2}})
print('Language model:',result['message']['content'],flush=True)
print(service.api('/api/ps'),flush=True)
