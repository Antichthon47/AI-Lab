"""Broker routing/forwarding tests with a fake upstream: no Ollama contact."""
import json
from pathlib import Path
import tempfile
import unittest
from security.bridge import Broker, MODELS, UnixConnection, authorize, MAX_BODY


class Response:
    def __init__(self,status=200):
        self.status=status
        self.data=b'data: {"fake":true}\n\ndata: [DONE]\n\n'

    def getheader(self,key,default=None):
        return "text/event-stream" if key == "Content-Type" else default

    def read1(self, _):
        data,self.data=self.data,b""
        return data


class FakeConnection:
    def __init__(self,calls,status=200):
        self.calls=calls; self.status=status

    def request(self,*args,**kwargs):
        self.calls.append((args,kwargs))

    def getresponse(self):
        return Response(self.status)

    def close(self):
        pass


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.calls=[]
        self.broker=Broker(Path(self.temp.name),upstream=lambda:FakeConnection(self.calls))
        self.broker.__enter__()
        self.addCleanup(self.broker.__exit__,None,None,None)

    def request(self,method,path,body=None,headers=None):
        connection=UnixConnection(self.broker.path)
        try:
            connection.request(method,path,body=body,headers=headers or {})
            response=connection.getresponse()
            return response.status,response.read()
        finally:
            connection.close()

    def valid(self,**extra):
        return json.dumps({"model":"pi-qwen35-9b-16k","messages":[],**extra}).encode()

    def test_discovery_is_local_and_filtered(self):
        code,body=self.request("GET","/v1/models")
        self.assertEqual(code,200)
        self.assertEqual({x['id'] for x in json.loads(body)['data']},MODELS)
        self.assertEqual(self.calls,[])

    def test_health_never_contacts_upstream(self):
        self.assertEqual(self.request("GET","/healthz"),(200,b'{"ok": true}'))
        self.assertEqual(self.calls,[])

    def test_fake_stream_forwarded(self):
        code,body=self.request("POST","/v1/chat/completions",self.valid(stream=True))
        self.assertEqual(code,200)
        self.assertIn(b'[DONE]',body)
        self.assertEqual(len(self.calls),1)

    def test_fake_responses_forwarded(self):
        self.assertEqual(self.request("POST","/v1/responses",self.valid())[0],200)

    def test_management_and_arbitrary_urls_denied(self):
        for path in ("/api/pull","/api/delete","/api/create","/api/show","/api/chat",
                     "http://127.0.0.1:22/","http://example.com/","//example.com/",
                     "/v1/chat/completions?upstream=example.com","/v1/../api/pull"):
            with self.subTest(path=path):
                self.assertEqual(self.request("POST",path,self.valid())[0],403)
        self.assertEqual(self.calls,[])

    def test_connect_denied(self):
        self.assertEqual(self.request("CONNECT","127.0.0.1:22")[0],403)
        self.assertEqual(self.calls,[])

    def test_unknown_model_denied(self):
        self.assertEqual(self.request("POST","/v1/responses",self.valid(model="not-installed"))[0],403)
        self.assertEqual(self.calls,[])

    def test_redirects_rejected(self):
        self.broker.server.upstream=lambda:FakeConnection(self.calls,302)
        self.assertEqual(self.request("POST","/v1/responses",self.valid())[0],502)

    def test_sensitive_headers_not_forwarded(self):
        self.request("POST","/v1/responses",self.valid(),{"Authorization":"secret","Host":"evil.invalid","Cookie":"private"})
        headers=self.calls[0][1]['headers']
        self.assertEqual(headers,{"Content-Type":"application/json"})

    def test_duplicate_json_keys_denied(self):
        body=b'{"model":"pi-qwen35-9b-16k","model":"other"}'
        self.assertEqual(self.request("POST","/v1/responses",body)[0],403)

    def test_unknown_fields_and_budget_denied(self):
        for extras in ({"base_url":"http://evil.invalid"},{"max_tokens":4096},{"max_tokens":True},{"max_tokens":0}):
            with self.subTest(extras=extras):
                self.assertEqual(self.request("POST","/v1/responses",self.valid(**extras))[0],403)

    def test_oversized_request_denied_before_read(self):
        self.assertEqual(self.request("POST","/v1/responses",b"",{"Content-Length":str(MAX_BODY+1)})[0],403)

    def test_chunked_and_expect_denied(self):
        for headers in ({"Transfer-Encoding":"chunked"},{"Expect":"100-continue"}):
            self.assertEqual(self.request("POST","/v1/responses",self.valid(),headers)[0],403)

    def test_get_body_denied(self):
        self.assertEqual(self.request("GET","/v1/models",b"bad")[0],403)

    def test_image_and_file_fetches_denied(self):
        for part in ({"type":"image_url","image_url":{"url":"http://127.0.0.1:22/"}},
                     {"type":"input_image","image_url":"https://example.com/a.png"},
                     {"type":"input_file","file_url":"http://127.0.0.1:22/"}):
            for key in ("messages", "input"):
                with self.subTest(part=part,key=key):
                    body=self.valid(**{key:[{"role":"user","content":[part]}]})
                    self.assertEqual(self.request("POST","/v1/responses",body)[0],403)
        self.assertEqual(self.calls,[])

    def test_server_side_tools_denied(self):
        for tool in ({"type":"web_search"},{"type":"mcp","server_url":"http://127.0.0.1:22/"}):
            self.assertEqual(self.request("POST","/v1/responses",self.valid(tools=[tool]))[0],403)
        self.assertEqual(self.calls,[])

    def test_default_output_budget(self):
        self.request("POST","/v1/responses",self.valid())
        self.assertEqual(json.loads(self.calls[0][1]['body'])['max_output_tokens'],2048)

    def test_remote_schema_reference_denied(self):
        tool={"type":"function","function":{"name":"local","parameters":{"$ref":"http://127.0.0.1:22/"}}}
        self.assertEqual(self.request("POST","/v1/responses",self.valid(tools=[tool]))[0],403)
        self.assertEqual(self.calls,[])

    def test_function_tools_and_text_allowed(self):
        tool={"type":"function","function":{"name":"read","parameters":{"type":"object"}}}
        data=self.valid(tools=[tool],messages=[{"role":"user","content":[{"type":"text","text":"hello"}]}])
        self.assertEqual(self.request("POST","/v1/chat/completions",data)[0],200)

    def test_nonfunction_replay_denied(self):
        data=self.valid(messages=[{"role":"assistant","content":None,"tool_calls":[{"type":"mcp"}]}])
        self.assertEqual(self.request("POST","/v1/chat/completions",data)[0],403)
        self.assertEqual(self.calls,[])


if __name__=="__main__":
    unittest.main()
