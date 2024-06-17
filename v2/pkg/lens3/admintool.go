/* Lens3-admin command.  It a database modifier. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
	"bufio"
	"encoding/csv"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"slices"
	"strconv"
	"strings"
	"time"
	//"log"
)

func Run_lens3_admin() {
	make_adm_command_table()
	adm_toplevel()
}

type adm struct {
	dbconf *db_conf
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
	Pools []*pool_prop   `json:"Pools"`
}

var cmd_table = map[string]*cmd{}

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
	var flag_conf = flag.String("c", "conf.json",
		"A file containing keyval-db connection info.")
	var flag_debug = flag.Bool("d", false,
		"Debug flag.")
	_ = flag_conf
	_ = flag_debug
	flag.Parse()

	var args = flag.Args()
	if len(args) == 0 {
		cmd_help(nil, args)
		return
	}

	assert_fatal(flag_conf != nil)
	var dbconf = read_db_conf(*flag_conf)
	//fmt.Println(dbconf)
	var t = make_keyval_table(dbconf)
	_ = t
	var adm = &adm{
		dbconf: dbconf,
		table:  t,
	}

	var subcmd = cmd_table[args[0]]
	if subcmd == nil {
		fmt.Fprintf(os.Stderr, "Command (%s) unknown\n", args[0])
		cmd_help(nil, args)
		return
	}
	subcmd.run(adm, args)
}

func show_user(t *keyval_table, filename string) {
	var userlist = list_users(t)
	var users []*user_record
	for _, uid := range userlist {
		var i = get_user(t, uid)
		if i != nil {
			users = append(users, i)
		}
	}

	// var w1, err1 = os.Create(filename)
	// if err1 != nil {
	// 	log.Panicf("Open a file (%s) failed: err=(%v)\n",
	// 		filename, err1)
	// }
	// defer w1.Close()

	var e = csv.NewWriter(os.Stdout)
	defer e.Flush()

	for _, u := range users {
		if u.Ephemeral {
			continue
		}
		var fields = []string{"ADD", u.Uid, u.Claim}
		fields = append(fields, u.Groups...)
		var err2 = e.Write(fields)
		if err2 != nil {
			fmt.Fprintf(os.Stderr, "Writing csv entry failed: err=(%v)\n",
				err2)
			panic(nil)
		}
	}

	var disables []string
	for _, u := range users {
		if u.Ephemeral || u.Enabled {
			continue
		}
		disables = append(disables, u.Uid)
	}
	if len(disables) > 0 {
		var fields = append([]string{"DISABLE"}, disables...)
		var err3 = e.Write(fields)
		if err3 != nil {
			fmt.Fprintf(os.Stderr, "Writing csv entry failed: err=(%v)\n",
				err3)
			panic(nil)
		}
	}
}

func load_user(t *keyval_table, filename string) {
	var r1, err1 = os.Open(filename)
	if err1 != nil {
		fmt.Fprintf(os.Stderr, "Open a file (%s) failed: err=(%v)\n",
			filename, err1)
		panic(nil)
	}
	defer r1.Close()
	var e = csv.NewReader(r1)
	// Set as variable number of columns.
	e.FieldsPerRecord = -1
	var users, err2 = e.ReadAll()
	if err2 != nil {
		fmt.Fprintf(os.Stderr, "Reading csv entry failed: err=(%v)\n", err2)
		panic(nil)
	}

	// Sort rows to process ADD rows first.

	var ordering = map[string]int{
		// Zero for missing key.
		"ADD":     1,
		"MODIFY":  1,
		"DELETE":  2,
		"ENABLE":  3,
		"DISABLE": 4,
	}
	slices.SortFunc(users, func(a, b []string) int {
		return ordering[a[0]] - ordering[b[0]]
	})

	for _, record := range users {
		switch record[0] {
		case "ADD", "MODIFY":
			// ADD,uid,claim,group,...
			var groupok = func() bool {
				for _, g := range record[3:] {
					if !check_user_naming(g) {
						return false
					}
				}
				return true
			}()
			if !(len(record) >= 4) ||
				!check_user_naming(record[1]) ||
				!check_claim_string(record[2]) ||
				!groupok {
				fmt.Fprintf(os.Stderr, "Bad user ADD entry: (%v)\n", record)
				panic(nil)
			}
			//.Unix()
			var years = 10
			var expiration = time.Now().AddDate(years, 0, 0).Unix()
			var now int64 = time.Now().Unix()
			var u = &user_record{
				Uid:                        record[1],
				Claim:                      record[2],
				Groups:                     record[3:],
				Enabled:                    true,
				Ephemeral:                  false,
				Expiration_time:            expiration,
				Check_terms_and_conditions: false,
				Timestamp:                  now,
			}
			if record[0] == "ADD" {
				deregister_user(t, u.Uid)
			}
			add_user(t, u)
		case "DELETE", "ENABLE", "DISABLE":
			// DELETE,uid,...
			// ENABLE,uid,...
			// DISABLE,uid,...
			var op = record[0]
			var ok = func() bool {
				for _, n := range record[1:] {
					if !check_user_naming(n) {
						return false
					}
				}
				return true
			}()
			if !ok {
				fmt.Fprintf(os.Stderr, "Bad user %s entry: (%v)\n", op, record)
				panic(nil)
			}
			for _, n := range record[1:] {
				var u = get_user(t, n)
				if u == nil {
					fmt.Fprintf(os.Stderr, "Unknown user (%s) in %s entry\n",
						n, op)
					continue
				}
				switch op {
				case "DELETE":
					deregister_user(t, n)
				case "ENABLE", "DISABLE":
					u.Enabled = (op == "ENABLE")
					add_user(t, u)
				}
			}
		default:
			var op = record[0]
			fmt.Fprintf(os.Stderr, "Bad user %s entry: (%v)\n", op, record)
			panic(nil)
		}
	}
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
	var poolprops []*pool_prop
	for _, pool := range poollist {
		var i = gather_pool_prop(t, pool)
		//fmt.Println("pool=", i)
		if i != nil {
			poolprops = append(poolprops, i)
		}
	}
	return &dump_data{
		Confs: confs,
		Users: users,
		Pools: poolprops,
	}
}

func print_in_json(x any) {
	//for _, x := range list {
	var b1, err1 = json.MarshalIndent(x, "", "    ")
	if err1 != nil {
		fmt.Fprintf(os.Stderr, "json.Marshal() failed, err=(%v)\n", err1)
		panic(nil)
	}
	fmt.Println(string(b1))
	//}
}

func dump_in_json_to_file(filename string, users any) {
	var w1 io.Writer
	if filename != "" {
		var w2, err1 = os.Create(filename)
		if err1 != nil {
			fmt.Fprintf(os.Stderr, "Open a file (%s) failed: err=(%v)\n",
				filename, err1)
			panic(nil)
		}
		defer w2.Close()
		w1 = w2
	} else {
		w1 = os.Stdout
	}
	var e = json.NewEncoder(w1)
	e.SetIndent("", "    ")
	var err2 = e.Encode(users)
	if err2 != nil {
		fmt.Fprintf(os.Stderr, "Writing json failed: err=(%v)\n", err2)
		panic(nil)
	}
}

func restore_db(t *keyval_table, filename string) {
	var r1, err1 = os.Open(filename)
	if err1 != nil {
		fmt.Fprintf(os.Stderr, "Open a file (%s) failed: err=(%v)\n",
			filename, err1)
		panic(nil)
	}
	defer r1.Close()
	var sc1 = bufio.NewScanner(r1)
	var evenodd int
	var kv = [2]string{"", ""}
	for sc1.Scan() {
		kv[evenodd] = sc1.Text()
		if evenodd == 1 {
			if !strings.HasPrefix(kv[1], "    ") {
				fmt.Fprintf(os.Stderr, "Missing prefix in 2nd line")
				panic(nil)
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

func delete_db_entry(t *keyval_table, key string) {
	adm_del_db_raw(t, key)
}

func probe_mux(t *keyval_table, pool string) {
	var err1 = probe_access_mux(t, pool)
	if err1 != nil {
		fmt.Println(err1)
	}
}

func wipe_out_db(t *keyval_table, everything string) {
	if everything == "everything" {
		clear_everything(t)
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

func show_unix_time(s1 string) {
	// To accept a dateTtime format as the date_time format.
	var s2 = strings.Replace(s1, "T", " ", 1)

	var t1, err1 = time.Parse(time.DateTime, s2)
	if err1 == nil {
		fmt.Printf("unix time of (%s) is (%v)\n", t1, t1.Unix())
		return
	}
	var t2, err2 = time.Parse(time.DateOnly, s2)
	if err2 == nil {
		fmt.Printf("unix time of (%s) is (%v)\n", t2, t2.Unix())
		return
	}

	var n, err3 = strconv.ParseInt(s2, 10, 64)
	if err3 == nil {
		var t3 = time.Unix(n, 0)
		fmt.Printf("unix time of (%s) is (%v)\n", t3, t3.Unix())
		return
	}
	return
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
		synopsis: "show-conf",
		doc:      `Prints all conf data in keyval-db.`,
		run: func(adm *adm, args []string) {
			var conflist = list_confs(adm.table)
			for _, e := range conflist {
				fmt.Println("// ----")
				switch c := (*e).(type) {
				case *mux_conf:
					fmt.Printf("// Conf %s\n", c.Subject)
					var c3, err3 = json.MarshalIndent(c, "", "    ")
					if err3 != nil {
						fmt.Fprintf(os.Stderr, "json.Marshal() failed: err=(%v)\n",
							err3)
						panic(nil)
					}
					fmt.Println(string(c3))
				case *reg_conf:
					fmt.Printf("// Conf %s\n", c.Subject)
					var c4, err4 = json.MarshalIndent(c, "", "    ")
					if err4 != nil {
						fmt.Fprintf(os.Stderr, "json.Marshal() failed: err=(%v)\n",
							err4)
						panic(nil)
					}
					fmt.Println(string(c4))
				default:
					panic(nil)
				}
			}
		},
	},

	&cmd{
		synopsis: "load-conf file-name.json",

		doc: `Loads a conf file in the keyval-db.`,

		run: func(adm *adm, args []string) {
			var conf = read_conf(args[1])
			if conf == nil {
				panic(nil)
			}
			set_conf(adm.table, conf)
		},
	},

	&cmd{
		synopsis: "show-user",

		doc: `Prints users in csv format.  It lists ADD rows first,
        and then a DISABLE row.`,

		run: func(adm *adm, args []string) {
			show_user(adm.table, "")
		},
	},

	&cmd{
		synopsis: "load-user file-name.csv",

		doc: `Loads users in csv format.  It adds or deletes users as
        in the list.  It reads rows starting with one of: "ADD",
        "MODIFY", "DELETE", "ENABLE", or "DISABLE".  Add and modify
        are almost the same.  Add rows consist of:
        ADD,uid,claim,group,... (the rest is a group list).  The claim
        is an X-Remote-User key or empty.  A group list needs at least
        one entry.  Adding and modifying work differently on existing
        users.  Adding resets the user and deletes the pools owned.
        Modifying keeps the pools.  DELETE, ENABLE and DISABLE take
        rows of a uid list: DELETE,uid,...  It processes all
        add/modify rows first, then the delete, enable, and disable in
        this order.  Do not put spaces around a comma or trailing
        commas in csv.`,

		run: func(adm *adm, args []string) {
			load_user(adm.table, args[1])
		},
	},

	&cmd{
		synopsis: "show-pool [pool-name ...]",
		doc:      `Prints pools.  It shows all pools without arguments.`,
		run: func(adm *adm, args []string) {
			var list []string
			if len(args) == 1 {
				list = list_pools(adm.table, "*")
			} else {
				list = args[1:]
			}
			var poolprops []*pool_prop
			for _, name := range list {
				var d = gather_pool_prop(adm.table, name)
				if d == nil {
					fmt.Fprintf(os.Stderr, "No pool found for pool=(%s)", name)
				} else {
					poolprops = append(poolprops, d)
				}
			}
			for _, x := range poolprops {
				print_in_json(x)
			}
		},
	},

	&cmd{
		synopsis: "show-bucket",
		doc:      `Prints all buckets.`,
		run: func(adm *adm, args []string) {
			var bkts = list_buckets(adm.table, "")
			//for _, x := range bkts {
			print_in_json(bkts)
			//}
		},
	},

	&cmd{
		synopsis: "show-directory",
		doc:      `Prints all buckets-directories.`,
		run: func(adm *adm, args []string) {
			var dirs = list_buckets_directories(adm.table)
			print_in_json(dirs)
			// for _, x := range dirs {
			// 	print_in_json(x)
			// 	//fmt.Printf("%v\n", x)
			// }
		},
	},

	&cmd{
		synopsis: "dump-user [file-name.json]",
		doc:      `Dumps users for restoring.`,
		run: func(adm *adm, args []string) {
			//fmt.Println("// dumping...")
			var userlist = list_users(adm.table)
			var users []*user_record
			for _, uid := range userlist {
				var i = get_user(adm.table, uid)
				if i != nil {
					users = append(users, i)
				}
			}
			var filename string
			if len(args) == 1 {
				filename = ""
			} else {
				filename = args[1]
			}
			dump_in_json_to_file(filename, users)
		},
	},

	&cmd{
		synopsis: "dump-pool [file-name.json]",
		doc:      `Dumps pools for restoring.`,
		run: func(adm *adm, args []string) {
			//fmt.Println("// dumping...")
			var poollist = list_pools(adm.table, "*")
			var poolprops []*pool_prop
			for _, pool := range poollist {
				var i = gather_pool_prop(adm.table, pool)
				if i != nil {
					poolprops = append(poolprops, i)
				}
			}
			var filename string
			if len(args) == 1 {
				filename = ""
			} else {
				filename = args[1]
			}
			dump_in_json_to_file(filename, poolprops)
		},
	},

	&cmd{
		synopsis: "dump-db",

		doc: `Dumps all key-value pairs in keyval-db.  It is a
		repeatation of key-value pairs, with a value part is idented
		by four whitespaces.  Keys are strings and values are records
		in json.`,

		run: func(adm *adm, args []string) {
			dump_db(adm.table)
		},
	},

	&cmd{
		synopsis: "restore-db file-name.txt",

		doc: `Restores key-value entries in keyval-db from a file.  A
		file should contain a repeatation of key-value pairs.  See the
		doc on dump-db about the output format.`,

		run: func(adm *adm, args []string) {
			restore_db(adm.table, args[1])
		},
	},

	&cmd{
		synopsis: "remove-db-entry key",
		doc:      `Removes an entry in the keyval-db by a key.`,
		run: func(adm *adm, args []string) {
			delete_db_entry(adm.table, args[1])
		},
	},

	&cmd{
		synopsis: "wipe-out-db 'everything' (type literally)",
		doc:      `Removes everything in the keyval-db.`,
		run: func(adm *adm, args []string) {
			wipe_out_db(adm.table, args[1])
		},
	},

	&cmd{
		synopsis: "probe-mux pool",
		doc: `Accesses one Mux for probing a pool.  It starts a
		backend.`,
		run: func(adm *adm, args []string) {
			probe_mux(adm.table, args[1])
		},
	},

	&cmd{
		synopsis: "show-unix-time 'yyyy-mm-dd hh:mm:ss' or int64",
		doc:      `Converts time in int64.`,
		run: func(adm *adm, args []string) {
			show_unix_time(args[1])
		},
	},
}
