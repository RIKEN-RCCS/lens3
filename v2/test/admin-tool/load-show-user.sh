#!/bin/ksh -x

# RUN IN TEST SETTING.  IT CLEARS THE KEYVAL-DB.

cmd=./a.out

cat <<EOF > test-users.csv
ADD,ohituji,ohituji,nezumi,ushi,tora
ADD,oushi,,nezumi
ENABLE,futago,kani,sasori
MODIFY,futago,,nezumi,ushi,tora
ADD,kani,,nezumi,ushi,tora
ADD,sisi,,nezumi,ushi,tora
ADD,otome,,nezumi,ushi,tora
ADD,tenbin,,nezumi,ushi,tora
ADD,sasori,,nezumi,ushi,tora
DISABLE,yagi,ite
ADD,ite,,nezumi,ushi,tora
ADD,yagi,yagi,nezumi,ushi,tora
ADD,mizugame,mizugame,nezumi,ushi,tora,nezumi,ushi,tora
ADD,uo,,nezumi,ushi,tora
EOF

cat <<EOF > test-users-correct.csv
ADD,futago,,nezumi,ushi,tora
ADD,ite,,nezumi,ushi,tora
ADD,kani,,nezumi,ushi,tora
ADD,mizugame,mizugame,nezumi,ushi,tora,nezumi,ushi,tora
ADD,ohituji,ohituji,nezumi,ushi,tora
ADD,otome,,nezumi,ushi,tora
ADD,oushi,,nezumi
ADD,sasori,,nezumi,ushi,tora
ADD,sisi,,nezumi,ushi,tora
ADD,tenbin,,nezumi,ushi,tora
ADD,uo,,nezumi,ushi,tora
ADD,yagi,yagi,nezumi,ushi,tora
DISABLE,yagi,ite
EOF

${cmd} wipe-out-db everything
${cmd} load-user test-users.csv
${cmd} show-user | sort > test-users-result.csv
diff -u test-users-correct.csv test-users-result.csv
