#!/bin/ksh -x

cat <<EOF > test-users.csv
ADD,ohituji,ohituji,nezumi,ushi,tora
ADD,oushi,,nezumi
ADD,futago,,nezumi,ushi,tora
ADD,kani,,nezumi,ushi,tora
ADD,sisi,,nezumi,ushi,tora
ADD,otome,,nezumi,ushi,tora
ADD,tenbin,,nezumi,ushi,tora
ADD,sasori,,nezumi,ushi,tora
ADD,ite,,nezumi,ushi,tora
ADD,yagi,yagi,nezumi,ushi,tora
ADD,mizugame,mizugame,nezumi,ushi,tora,nezumi,ushi,tora
ADD,uo,,nezumi,ushi,tora
DISABLE,yagi,ite
ENABLE,futago,kani,sasori
EOF
./a.out load-user test-users.csv
