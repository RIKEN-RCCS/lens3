// Copyright (c) 2022 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

///// Editor /////

var csrf_token;

var editor_data = {
	seen: false,
	zoneID: "",
	user: "",
	group: "",
	bucketsDir: "",
	buckets: ["", "", "", ""],
	accessKeys: [],
accessKeyIDrw: "",
accessKeyIDro: "",
accessKeyIDwo: "",
secretAccessKeyrw: "",
secretAccessKeyro: "",
secretAccessKeywo: "",
key: "",
policy: "",
	directHostnames: "",
	expDate: "",
	status: "",
	mode: "",
	atime: "",
	groups: "",
	directHostnameDomains: "",
	delegateHostnames: "",
	endpointURLs: "",
	createButtonName: "",
	createButtonDisabled: false,
	createButtonVisible: false,
	deleteButtonDisabled: false,
	bucketsDirectoryDisabled: false,
};

var editor_app = new Vue({
	el: '#editor',
	data: editor_data,
	methods: {
		submitZoneToCreate: submit_zone_to_create,
		submitCreateBucket: create_bucket,
		submitChangeAccessKeyRW: change_access_key_rw,
		submitChangeAccessKeyRO: change_access_key_ro,
		submitChangeAccessKeyWO: change_access_key_wo,
	},
});


///// Show Storage Zone (button) /////
var show_data = {
	message: "---",
	status: "---",
	reason: "---",
	time: "---",
};

var show_app = new Vue({
	el: "#show_button",
	data: show_data,
	methods: {
		show: get_zone_list,
		debug: debug,
	},
});


///// Add Storage Zone (button) /////
var add_app = new Vue({
	el: "#add_button",
	methods: {
		add_zone: get_template,
	},
});


///// Zone /////

// dynamically allocated
var zone_data = { seen: false }; // sentinel
var zone_app;

///// FUNCTIONS /////

function submit_zone_to_create() {
	var create = editor_data["createButtonName"] == "Create";
	console.log("CREATE = " + create);
	if (create) {
		return submit_zone(0)
	}
	else {
		return submit_zone(1)
	}
}

function create_bucket() {
	console.log("change_access_key WO");
	return submit_zone(2)
}

function change_access_key_rw() {
	console.log("change_access_key RW");
	return submit_zone(3)
}

function change_access_key_ro() {
	console.log("change_access_key RO");
	return submit_zone(4)
}

function change_access_key_wo() {
	console.log("change_access_key WO");
	return submit_zone(5)
}

function submit_zone(op) {
	disable_create_button();
	show_message(editor_data["createButtonName"] + " zone...");
	clear_status_field();

	var method;
	var url_path;
	var body;

	if (op == 0) {		// create
		method = "POST";
		url_path = "/zone";
		body = compose_create_dict(csrf_token);
	}
	else if (op == 1) {	// updte zone
		method = "PUT";
		url_path = "/zone/" + editor_data.zoneID;
		body = compose_update_dict(csrf_token);
	}
	else if (op == 2) {	// create bucket
		var key = editor_data.key;
		var policy = editor_data.policy;
		method = "PUT";
		url_path = "/zone/" + editor_data.zoneID + "/buckets";
		body = compose_create_bucket_dict(csrf_token, key, policy);
	}
	else if (op == 3 || op == 4 || op == 5) {
		var accessKeyID;
		if (op == 3) {
			accessKeyID = editor_data.accessKeyIDrw;
		}
		else if (op == 4) {
			accessKeyID = editor_data.accessKeyIDro;
		}
		else if (op == 5) {
			accessKeyID = editor_data.accessKeyIDwo;
		}

		method = "PUT";
		url_path = "/zone/" + editor_data.zoneID + "/accessKeys";
		body = compose_access_key_update_dict(csrf_token, accessKeyID);
	}

	console.log("method: " + method);
	console.log("url_path: " + url_path);
	console.log("body: " + body);
	var requestOptions = {
		method: method,
		body: body,
	};

	fetch(url_path, requestOptions)
		.then(function(response) {
			if (!response.ok) {
				return response.json().then(
					function(data) {
						show_message(editor_data.createButtonName + " zone... error: " + JSON.stringify(data));
						render_jsondata(data)
						editor_data.mode = data["zonelist"][0]["mode"]
						enable_create_button();
						set_create_button_visibility(true);
						throw new Error(JSON.stringify(data));
				})
			}
			response.json().then(function(data) {
				show_message(editor_data.createButtonName + " zone... done: " + JSON.stringify(data));
				render_jsondata(data)
				editor_data.mode = data["zonelist"][0]["mode"]
				// update succeeded. do not re-enable button now.
			})
		})
		.catch(function(err) {
			console.log("Fetch Error: ", err);
		});
}

const policies = ["none", "public", "upload", "download"];

const policyNames = ["readwrite", "readonly", "writeonly"];

function stringify_dict(dict, csrf_token) {
	dict["CSRF-Token"] = csrf_token;
	return JSON.stringify(dict);
}

function pullup_zone() {
	var zone = {};
	var buckets = new Array();
	var directHostnames = new Array();
	for (var i = 0; i < policies.length; i++) {
		buckets = push_buckets(buckets, editor_data.buckets[i], policies[i]);
	}
	directHostnames = push_direct_hostnames(directHostnames,
				editor_data.directHostnameDomains,
				editor_data.directHostnames);
	zone["group"] = editor_data.group;
	zone["bucketsDir"] = editor_data.bucketsDir;
	zone["buckets"] = buckets;
	zone["accessKeys"] = [{"policyName": "readwrite"}, {"policyName": "readonly"}, {"policyName": "writeonly"}]; // dummy entry
	zone["directHostnames"] = directHostnames;
	zone["expDate"] = parse_rfc3339(editor_data.expDate);
	zone["status"] = editor_data.status;
	// ignore "mode", nor "atime"
	return zone;
}

function compose_create_dict(csrf_token) {
	var zone = pullup_zone();
	var dict = {"zone": zone};
	return stringify_dict(dict, csrf_token);
}

function compose_update_dict(csrf_token) {
	var zone = pullup_zone();
	zone["accessKeys"] = editor_data.accessKeys; // overwrite a dummy entry
	var dict = {"zone": zone};
	return stringify_dict(dict, csrf_token);
}

function compose_create_bucket_dict(csrf_token, key, policy) {
	if (policy != "none" && policy != "upload" && policy != "download") {
		throw new Error("error: invalid policy: " + policy);
	}
	var zone = {"buckets": [{"key": key, "policy": policy}]};
	var dict = {"zone": zone};
	return stringify_dict(dict, csrf_token);
}

function compose_access_key_update_dict(csrf_token, accessKeyID ) {
	var zone = {"accessKeys": [{"accessKeyID": accessKeyID}]};
	var dict = {"zone": zone};
	return stringify_dict(dict, csrf_token);
}

function compose_delete_dict(csrf_token) {
	var dict = {};
	return stringify_dict(dict, csrf_token);
}

function push_buckets(buckets, bucketList, policy) {
	var xs = bucketList.split(' ');
	for (var i = 0; i < xs.length; i++) {
		var bucket = xs[i];
		if (bucket != "") {
			var v = {"key": bucket, "policy": policy};
			buckets.push(v);
		}
	}
	return buckets;
}

function push_direct_hostnames(directHostnames, directHostnameDomains, hosts) {
	var xs = hosts.split(' ');
	for (var i = 0; i < xs.length; i++) {
		var directHostname = xs[i];
		if (directHostname != "") {
			if (!directHostname.endsWith("." + directHostnameDomains[0])) {
				directHostname += "." + directHostnameDomains[0];
			}
			directHostnames.push(directHostname);
		}
	}
	return directHostnames;
}

function debug() {
	var post_data = compose_create_dict(csrf_token);
	var put_data = compose_update_dict(csrf_token);
	var bkt_data = compose_create_bucket_dict(csrf_token);
	var key_data = compose_access_key_update_dict(csrf_token);
	var delete_data = compose_delete_dict(csrf_token);
	console.log("post_data: " + post_data);
	console.log("put_data: " + put_data);
	console.log("bkt_data: " + bkt_data);
	console.log("key_data: " + key_data);
	console.log("delete_data: " + delete_data);
	//parsed = Date.parse("2012-07-04T18:10:00.000+09:00")
	//console.log("parsed: " + parsed);
	//var e = "1638401795";
	//var date = new Date(e * 1000);
	//var formatted = date.toISOString();
	//console.log("toISOString: " + e + " => " + formatted);
	//var t = "2012-07-04T18:10:00.000+09:00";
	//var parsed = Date.parse(s)
	//var date2 = new Date(s)
	//var d2 = date2.getTime() / 1000;
	//console.log("new Date: " + s + " => " + d2);
	var s = "2022-03-31T00:00:00.000Z";
	var t = parse_rfc3339(s);
	var u = format_rfc3339(t);
	console.log("parse: " + s + " => " + t);
	console.log("unparse: " + t + " => " + u);
}

function get_zone_list() {
	show_message("get zone list...");
	clear_status_field();
	const method = "GET";
	const url_path = "/zone";
	const requestOptions = {
		method: method,
		headers: {},
	};
	fetch(url_path, requestOptions)
		.then(function(response) {
			if (!response.ok) {
				return response.json().then(
					function(data) {
						show_message("get zone list... error: " + JSON.stringify(data));
						render_jsondata(data)
						throw new Error(JSON.stringify(data));
				})
			}
			response.json().then(function(data) {
				csrf_token = data["CSRF-Token"];
				get_zone_list_body(data["zonelist"]);
				show_message("get zone list... done");
			})
		})
		.catch(function(err) {
			console.log("Fetch Error: ", err);
		});
}

function get_template() {
	disable_create_button();
	show_message("get new zone...");
	clear_status_field();
	const method = "GET";
	const url_path = "/template";
	const requestOptions = {
		method: method,
		headers: {},
	};
	fetch(url_path, requestOptions)
		.then(function(response) {
			if (!response.ok) {
				return response.json().then(
					function(data) {
						show_message("get new zone... error: " + JSON.stringify(data));
						render_jsondata(data)
						// fatal error. do not re-enable the button. enable_update_button();
						throw new Error(JSON.stringify(data));
				})
			}
			response.json().then(function(data) {
				csrf_token = data["CSRF-Token"];
				get_template_body(data["zonelist"]);
				show_message("get new zone... done");
				enable_create_button();
				set_create_button_visibility(true);
			})
		})
		.catch(function(err) {
			console.log("Fetch Error: ", err);
		});
}

function get_template_body(zone_list) {
	zone = zone_list[0];
	set_zone_to_editor_body(zone);
	editor_data.bucketsDirectoryDisabled = false;

	editor_data.createButtonName = "Create";
	editor_data.seen = true;
	zone_data.seen = false;
}

function disable_create_button() {
	editor_data.createButtonDisabled = true;
}

function enable_create_button() {
	editor_data.createButtonDisabled = false;
}

function set_create_button_visibility(v) {
	editor_data.createButtonVisible = v;
}

function disable_delete_button() {
	editor_data.deleteButtonDisabled = true;
}

function enable_delete_button() {
	editor_data.deleteButtonDisabled = false;
}

function delete_zone_body(zone) {
	disable_delete_button();
	show_message("delete zone...");
	clear_status_field();
	var zoneID = zone["zoneID"];
	console.log(`zoneID = ${zoneID}`);
	const requestOptions = {
		method: "DELETE",
		body: compose_delete_dict(csrf_token),
	};
	var url_path = "/zone/" + zoneID;
	fetch(url_path, requestOptions)
		.then(function(response) {
			if (!response.ok) {
				return response.json().then(
					function(data) {
						show_message("delete zone... error: " + JSON.stringify(data));
						render_jsondata(data)
						enable_delete_button();
						throw new Error(JSON.stringify(data));
				})
			}
			response.json().then(function(data) {
				show_message("delete zone... done");
				enable_delete_button();
				get_zone_list();
			})
		})
		.catch(function(err) {
			console.log("Fetch Error: ", err);
		});
}

function get_zone_list_body(zone_list) {
	var div = "";
	var res = new Array();
	var items_list = new Array();
	editor_data.seen = false;
	for (var k = 0; k < zone_list.length; k++) {
		var zone = zone_list[k];
		var i = "<input v-on:click='editZone(" + k + ")' type='button' class='button' value='Edit' />" +
			"<input v-on:click='deleteZone(" + k + ")' type='button' class='button' value='Delete' :disabled='WRONG_deleteButtonDisabled' />" +
			"<ul style='list-style: none;'>" +
			"<li v-for='item in items_list[" + k + "]'>" +
			"<span class='label'> {{ item.text.label }}: </span>" +
			" {{ item.text.value }} " +
			"</li>" +
			"</ul>" +
			"<hr>";
		res.push(i);
		items_list.push(zone_to_ul_data(zone));
	}
	var div = "<div id='viewer' v-if='seen'>" +
		res.join("") +
		"</div>";
	var el = document.getElementById("zone_list")
	el.innerHTML = "";
	el.insertAdjacentHTML("beforeend", div);

	zone_data = {
		items_list: items_list,
		zone_list: zone_list,
		seen: false,
	};

	function edit_zone(i) {
		set_zone_to_editor_body(zone_data.zone_list[i]);
		editor_data.bucketsDirectoryDisabled = true;

		editor_data.createButtonName = "Update";
		enable_create_button();
		set_create_button_visibility(true);
		editor_data.seen = true;
		zone_data.seen = false;
	}
	function delete_zone(i) {
		delete_zone_body(zone_data.zone_list[i])
	}

	zone_app = new Vue({
		el: "#viewer",
		data: zone_data,
		methods: {
			editZone: edit_zone,
			deleteZone: delete_zone,
		}
	});
	zone_app.$mount();
	zone_data.zone_list = zone_list;
	zone_data.seen = true;
}

function zone_to_ul_data(zone) {
	var buckets = zone["buckets"];
	var accessKeys = zone["accessKeys"];
	var rwkey = chooseAccessKey(accessKeys, "readwrite");
	var rokey = chooseAccessKey(accessKeys, "readonly");
	var wokey = chooseAccessKey(accessKeys, "writeonly");

	return [
		{text: {label: "Zone ID", value: zone["zoneID"]}},
		{text: {label: "Endpoint-URL", value: zone["endpoint_url"]}},
		{text: {label: "Unix User", value: zone["user"]}},
		{text: {label: "Unix Group", value: zone["group"]}},
		{text: {label: "Buckets Directory", value: zone["bucketsDir"]}},
		{text: {label: "Private Buckets", value: scan_buckets(buckets, "none")}},
		{text: {label: "Public Buckets", value: scan_buckets(buckets, "public")}},
		{text: {label: "Upload Only Buckets", value: scan_buckets(buckets, "upload")}},
		{text: {label: "Download Only Buckets", value: scan_buckets(buckets, "download")}},
		{text: {label: "Access Key ID (RW)", value: rwkey["accessKeyID"]}},
		{text: {label: "Secret Access Key", value: rwkey["secretAccessKey"]}},
		{text: {label: "Access Key ID (RO)", value: rokey["accessKeyID"]}},
		{text: {label: "Secret Access Key", value: rokey["secretAccessKey"]}},
		{text: {label: "Access Key ID (WO)", value: wokey["accessKeyID"]}},
		{text: {label: "Secret Access Key", value: wokey["secretAccessKey"]}},
		{text: {label: "Direct Hostname", value: zone["directHostnames"].join(' ')}},
		{text: {label: "Expiration Data", value: format_rfc3339_if_not_zero(zone["expDate"])}},
		{text: {label: "Status", value: zone["status"]}},
		{text: {label: "Mode", value: zone["mode"]}},
		{text: {label: "Last Access Time", value: format_rfc3339_if_not_zero(zone["atime"])}},
	];
}

function set_zone_to_editor_body(zone) {
	var accessKeys = zone["accessKeys"];
	var rwkey = chooseAccessKey(accessKeys, "readwrite");
	var rokey = chooseAccessKey(accessKeys, "readonly");
	var wokey = chooseAccessKey(accessKeys, "writeonly");

	editor_data.zoneID = zone["zoneID"];
	editor_data.user = zone["user"];
	editor_data.group = zone["group"];
	editor_data.bucketsDir = zone["bucketsDir"];
	var buckets = zone["buckets"];
	for (var i = 0; i < policies.length; i++) {
		editor_data.buckets[i] = scan_buckets(buckets, policies[i]);
	}

	// for chenge secret
	editor_data.accessKeys = accessKeys;
	editor_data.accessKeyIDrw = rwkey["accessKeyID"];
	editor_data.accessKeyIDro = rokey["accessKeyID"];
	editor_data.accessKeyIDwo = wokey["accessKeyID"];
	editor_data.secretAccessKeyrw = rwkey["secretAccessKey"];
	editor_data.secretAccessKeyro = rokey["secretAccessKey"];
	editor_data.secretAccessKeywo = wokey["secretAccessKey"];

	editor_data.key = "";		// for bucket creation
	editor_data.policy = "";	// ditto.

	editor_data.directHostnames = zone["directHostnames"].join(' ');
	editor_data.expDate = format_rfc3339_if_not_zero(zone["expDate"]);
	editor_data.status = zone["status"];
	editor_data.mode = zone["mode"];
	editor_data.atime = format_rfc3339_if_not_zero(zone["atime"]);
	editor_data.groups = zone["groups"];
	editor_data.directHostnameDomains = zone["directHostnameDomains"];
	editor_data.delegateHostnames = zone["delegateHostnames"];
	editor_data.endpointURLs = zone["endpoint_url"];
	show_message("editing");
}

function show_message(s) {
	show_data.message = "Message: " + s;
}

function clear_status_field() {
	render_jsondata({"status": "", "reason": "", "time": "0"})
}

function render_jsondata(data) {
	show_status(data["status"])
	show_reason(data["reason"])
	show_time(data["time"])
}

function show_status(s) {
	show_data.status = "Status: " + s;
}

function show_reason(s) {
	show_data.reason = "Reason: " + s;
}

function show_time(s) {
	show_data.time = "Finished At: " + format_rfc3339_if_not_zero(s);
}

function parse_rfc3339(s) {
	return "" + new Date(s).getTime() / 1000;
}

function format_rfc3339(d) {
	return new Date(d * 1000).toISOString();
}

function format_rfc3339_if_not_zero(d) {
	//console.log("format_rfc3339_if_not_zero: " + d);
	if (d == "0") {
		return "0";
	}
	return format_rfc3339(d);
}

function chooseAccessKey(accessKeys, policyName) {
	for (var i = 0; i < accessKeys.length; i++) {
		var accessKey = accessKeys[i];
		if (accessKey["policyName"] == policyName) {
			return accessKey;
		}
	}
	return undefined;
}

function scan_buckets(buckets, policy) {
	var res = new Array();
	for (var i = 0; i < buckets.length; i++) {
		var bucket = buckets[i];
		if (bucket["policy"] == policy) {
			res.push(bucket["key"]);
		}
	}
	return res.join(' ');
}
