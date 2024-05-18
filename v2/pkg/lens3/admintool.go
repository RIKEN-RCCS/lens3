/* Lens3-admin command.  It a database modifier. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"strings"
	// "strconv"
	// "time"
)

type adm struct {
	dbconf db_conf
	table  *keyval_table
}

type cmd struct {
	synopsis string
	doc      string
	run      func(adm *adm, args []string)
}

type dump_data struct {
	Confs []*lens3_conf  `json:"Confs"`
	Users []*user_record `json:"Users"`
	Pools []*pool_desc   `json:"Pools"`
}

var cmd_table = map[string]*cmd{}

func Run() {
	make_adm_command_table()
	adm_toplevel()
}

func make_adm_command_table() {
	for _, cmd := range cmd_list {
		var p = strings.Index(cmd.synopsis, " ")
		var i = ITE(p != -1, p, len(cmd.synopsis))
		var name = cmd.synopsis[:i]
		cmd_table[name] = cmd
	}
}

func adm_toplevel() {
	//os.Args[...]
	var conf = flag.String("conf", "conf.json",
		"A file name of keyval-db connection info.")
	var yes = flag.Bool("yes", false, "force critical action")
	var everything = flag.Bool("everything", false, "do all")
	var debug = flag.Bool("debug", false, "debug")
	_ = conf
	_ = yes
	_ = everything
	_ = debug
	flag.Parse()

	var args = flag.Args()
	if len(args) == 0 {
		cmd_help(nil, args)
		return
	}

	assert_fatal(conf != nil)
	var dbconf = read_db_conf(*conf)
	//fmt.Println(dbconf)
	var t = make_table(dbconf)
	_ = t
	var adm = &adm{
		dbconf: dbconf,
		table:  t,
	}

	var subcmd = cmd_table[args[0]]
	if subcmd == nil {
		fmt.Printf("Command (%s) unknown.\n", args[0])
		cmd_help(nil, args)
		return
	}
	subcmd.run(adm, args)
}

// DUMP_DB returns a record of confs, users, and pools for restoring.
func dump_db__(t *keyval_table) *dump_data {
	// Collect confs:
	var confs = list_confs(t)
	// Collect users:
	var userlist = list_users(t)
	var users []*user_record
	for _, uid := range userlist {
		var i = get_user(t, uid)
		if i != nil {
			users = append(users, i)
		}
	}
	// Collect pools:
	var poollist = list_pools(t, "*")
	//fmt.Println("poollist=", poollist)
	var pools []*pool_desc
	for _, pool := range poollist {
		var i = gather_pool_desc(t, pool)
		//fmt.Println("pool=", i)
		if i != nil {
			pools = append(pools, i)
		}
	}
	return &dump_data{
		Confs: confs,
		Users: users,
		Pools: pools,
	}
}

func print_in_json(x any) {
	//for _, x := range list {
	var b4, err4 = json.MarshalIndent(x, "", "    ")
	if err4 != nil {
		panic(err4)
	}
	fmt.Println(string(b4))
	//}
}

func dump_in_json_to_file(filename string, users any) {
	var w1, err1 = os.Create(filename)
	if err1 != nil {
		log.Panicf("Open a file (%s) failed: err=(%v).\n",
			filename, err1)
	}
	defer w1.Close()
	var e = json.NewEncoder(w1)
	e.SetIndent("", "    ")
	var err2 = e.Encode(users)
	if err2 != nil {
		log.Panicf("Writing json failed: err=(%v).\n", err2)
	}
}

func restore_db(t *keyval_table, filename string) {
	var r1, err1 = os.Open(filename)
	if err1 != nil {
		log.Panicf("Open a file (%s) failed: err=(%v).\n",
			filename, err1)
	}
	defer r1.Close()
	var sc1 = bufio.NewScanner(r1)
	var evenodd int
	var kv = [2]string{"", ""}
	for sc1.Scan() {
		kv[evenodd] = sc1.Text()
		if evenodd == 1 {
			if !strings.HasPrefix(kv[1], "    ") {
				panic("missing prefix in 2nd line")
			}
			kv[1] = strings.TrimLeft(kv[1], " ")
			set_db_raw(t, kv)
			kv[0] = ""
			kv[1] = ""
		}
		if evenodd == 0 {
			evenodd = 1
		} else {
			evenodd = 0
		}
	}
}

// PRINT_DB prints all keyval-db entries.  Each entry is printed as a
// key+value record in json.  Note that a value is a string of a json
// record.  (* Each entry two lines; the 1st line is ^key$ and 2nd
// line is prefix by 4whitespaces as ^____value$. *)
func dump_db(t *keyval_table) {
	var i1 = scan_db_raw(t, "setting")
	print_db_entries(i1, "Setting")
	var i2 = scan_db_raw(t, "storage")
	print_db_entries(i2, "Storage")
	var i3 = scan_db_raw(t, "process")
	print_db_entries(i3, "Process")
}

func print_db_entries(db *db_raw_iterator, title string) {
	fmt.Println("//----")
	fmt.Println("// " + title)
	fmt.Println("//----")
	for {
		var kv = next_db_raw(db)
		if kv == nil {
			break
		}
		//print_in_json(kv)
		for key, val := range kv {
			fmt.Printf("%s\n", key)
			fmt.Printf("    %s\n", string(val))
			break
		}
	}
}

// (cmd_help cannot be in cmd_list, which makes a reference-cycle).
func cmd_help(adm *adm, args []string) {
	fmt.Println("List of commands:")
	for _, c := range cmd_list {
		fmt.Println(c.synopsis)
	}
}

var cmd_list = []*cmd{
	&cmd{
		synopsis: "show-confs",
		doc:      "Prints a list of conf data.",
		run: func(adm *adm, args []string) {
			var conflist = list_confs(adm.table)
			for _, e := range conflist {
				fmt.Println("// ----")
				switch c := (*e).(type) {
				case *mux_conf:
					fmt.Printf("// Conf %s\n", c.Subject)
					var c3, err3 = json.MarshalIndent(c, "", "    ")
					if err3 != nil {
						panic(err3)
					}
					fmt.Println(string(c3))
				case *reg_conf:
					fmt.Printf("// Conf %s\n", c.Subject)
					var c4, err4 = json.MarshalIndent(c, "", "    ")
					if err4 != nil {
						panic(err4)
					}
					fmt.Println(string(c4))
				default:
					panic("BAD")
				}
			}
		},
	},

	&cmd{
		synopsis: "load-conf file-name",
		doc:      "Loads a conf file (json) in keyval-db.",
		run: func(adm *adm, args []string) {
			var conf = read_conf(args[1])
			set_conf(adm.table, conf)
		},
	},

	&cmd{
		synopsis: "show-pool [pool-name ...]",
		doc:      "Prints pools.  It shows all pools without arguments.",
		run: func(adm *adm, args []string) {
			var list []string
			if len(args) == 1 {
				list = list_pools(adm.table, "*")
			} else {
				list = args[1:]
			}
			var descs []*pool_desc
			for _, name := range list {
				var d = gather_pool_desc(adm.table, name)
				if d == nil {
					fmt.Printf("No pool found for {pid}")
				} else {
					descs = append(descs, d)
				}
			}
			for _, x := range descs {
				print_in_json(x)
			}
		},
	},

	&cmd{
		synopsis: "show-buckets",
		doc:      "Prints all buckets.",
		run: func(adm *adm, args []string) {
			var bkts = list_buckets(adm.table, "")
			//for _, x := range bkts {
			print_in_json(bkts)
			//}
		},
	},

	&cmd{
		synopsis: "show-directory",
		doc:      "Prints all buckets-directories.",
		run: func(adm *adm, args []string) {
			var dirs = list_buckets_directories(adm.table)
			for _, x := range dirs {
				print_in_json(x)
			}
		},
	},

	&cmd{
		synopsis: "dump-users file-name",
		doc:      "Dumps confs, users and pools for restoring.",
		run: func(adm *adm, args []string) {
			fmt.Println("// dumping...")
			//var record = dump_db(adm.table)
			var userlist = list_users(adm.table)
			var users []*user_record
			for _, uid := range userlist {
				var i = get_user(adm.table, uid)
				if i != nil {
					users = append(users, i)
				}
			}
			dump_in_json_to_file(args[1], users)
		},
	},

	&cmd{
		synopsis: "dump-pools file-name",
		doc:      "Dumps confs, users and pools for restoring.",
		run: func(adm *adm, args []string) {
			fmt.Println("// dumping...")
			var poollist = list_pools(adm.table, "*")
			var pools []*pool_desc
			for _, pool := range poollist {
				var i = gather_pool_desc(adm.table, pool)
				if i != nil {
					pools = append(pools, i)
				}
			}
			dump_in_json_to_file(args[1], pools)
		},
	},

	&cmd{
		synopsis: "dump-db",
		doc: `Dumps all keyval-db in raw form.  It is a repeatation of
		a key and a value, where both are strings and a value is a
		string of json data.  A value part is idented by four
		whitespaces`,
		run: func(adm *adm, args []string) {
			dump_db(adm.table)
		},
	},

	&cmd{
		synopsis: "restore-db file-name",
		doc: `Restores key-value entries in the keyval-db from a file.
		A file contains repeatation of a key and a value.  See outputs
		from dump-db.  db-name is one of "setting", "storage",
		"process", "routing", or "monokey".`,
		run: func(adm *adm, args []string) {
			restore_db(adm.table, args[1])
		},
	},
}
