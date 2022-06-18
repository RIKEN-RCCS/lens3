CFLAGS+=-O2 -g
CFLAGS+=-Wall
CFLAGS+=-Wno-implicit-int
CFLAGS+=-Wdeclaration-after-statement

TFLAGS=--configfile=test.yaml \
	--max_sleep=5 \
	--max_nap=1

PFLAGS=--configfile=performance.yaml \
	--max_sleep=5 \
	--max_nap=1 \
	--sleep_until_next_slot=60 \
	--verbose=True \
	--interval_between_wakeups=180

all:: test1 admin restore

test1::
	python3 main.py $(TFLAGS) --user=u0000

test2::
	python3 main.py $(TFLAGS) --user=u0000 & \
	python3 main.py $(TFLAGS) --user=u0001 & \
	wait

test4::
	python3 main.py $(TFLAGS) --user=u0000 & \
	python3 main.py $(TFLAGS) --user=u0001 & \
	python3 main.py $(TFLAGS) --user=u0002 & \
	python3 main.py $(TFLAGS) --user=u0003 & \
	wait

perf1::
	python3 main.py $(PFLAGS) --user=u0000 & \
	wait

perf2::
	python3 main.py $(PFLAGS) --user=u0000 & \
	python3 main.py $(PFLAGS) --user=u0001 & \
	wait

perf3::
	python3 main.py $(PFLAGS) --user=u0000 & \
	python3 main.py $(PFLAGS) --user=u0001 & \
	python3 main.py $(PFLAGS) --user=u0002 & \
	wait

perf4::
	python3 main.py $(PFLAGS) --user=u0000 & \
	python3 main.py $(PFLAGS) --user=u0001 & \
	python3 main.py $(PFLAGS) --user=u0002 & \
	python3 main.py $(PFLAGS) --user=u0003 & \
	wait

perf8::
	python3 main.py $(PFLAGS) --user=u0000 & \
	python3 main.py $(PFLAGS) --user=u0001 & \
	python3 main.py $(PFLAGS) --user=u0002 & \
	python3 main.py $(PFLAGS) --user=u0003 & \
	python3 main.py $(PFLAGS) --user=u0004 & \
	python3 main.py $(PFLAGS) --user=u0005 & \
	python3 main.py $(PFLAGS) --user=u0006 & \
	python3 main.py $(PFLAGS) --user=u0007 & \
	wait

admin::
	python3 adm.py

restore::
	echo "DO NOT FORGET 'sudo usermod -a -G _lent8 $$(whoami)'"
	./dump-restore-test.sh

install:
	pip3 -qq install -r requirements.txt --user

tags::
	ctags *.py

FORMAT=--format=json
FORMAT=

PYFILES=lens3client.py apitest.py

pyright::
	-(pyright $(PYFILES)) > pyright-output.txt
	@grep -E ".* errors?, .* warnings?, .* informations?" pyright-output.txt

pyright-update::
	pip3 install --user -U pyright

clean::
	rm tags
