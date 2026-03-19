.PHONY: schema controller

init:
	pip install --upgrade pip
	pip3 install -r requirements.txt

dirs:
	mkdir -p logs

test:
	.penv/bin/python -m pytest -q

test-verbose:
	.penv/bin/python -m pytest -v

schema:
	protoc --proto_path=schema --python_out=agent schema/usp-msg-1-4.proto
	protoc --proto_path=schema --python_out=agent schema/usp-record-1-4.proto
	@echo "Moving generated files to standard names..."
	@mv agent/usp_msg_1_4_pb2.py agent/usp_msg_pb2.py 2>/dev/null || true
	@mv agent/usp_record_1_4_pb2.py agent/usp_record_pb2.py 2>/dev/null || true

lint:
	find agent -name "*.py" | egrep -v 'pb2' | xargs pylint || :

run:
	python3 -m agent.main -t test

runbin:
	python3 bin/agent.py -t test

controller:
	python3 bin/controller.py 

runcoap:
	python3 bin/agent.py -t test -c --coap-port 15683

