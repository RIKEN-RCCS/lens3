#! /bin/sh

#set -o errexit
#set -o nounset

export TMPDIR=/dsk/tmp

numuser=10

if [ $# = 1 ]; then
	numuser=$1
fi

#max_sleep=30
#max_nap=5
max_sleep=8
max_nap=2

start_interval=3

cp /dev/null /tmp/all.log

echo "numuser: $numuser" >>/tmp/all.log

date +%Y%m%dT%H%M%S >>/tmp/all.log

for u in $(seq 0 $((numuser - 1))); do
	user=$(printf u%04d $u)
	pass=$(printf p%04d $u)
	sleep $start_interval
	echo $user 1>&2
	echo $user: $(date)
	(
	 python3 main.py 2>&1 \
		--configfile test.yaml \
		--user=$user \
		--max_nap=$max_nap \
		--max_sleep=$max_sleep |
		sed "s/^/$user: /"
	) &
done >>/tmp/all.log
wait

date +%Y%m%dT%H%M%S >>/tmp/all.log

grep FAIL /tmp/all.log
