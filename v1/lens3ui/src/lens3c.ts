export const pool_data = {
  buckets_directory: "/home/users/m-matsuda/pool-x",
  user: "m-matsuda",
  group: "aot",
  group_choices: ["m-matsuda", "aot"],
  kick_make_pool: () => {},

  desserts: [
    {name: "Buckets directory", calories: "/home/users/m-matsuda/pool-a"},
    {name: "Unix user", calories: "m-matsuda"},
    {name: "Unix group", calories: "m-matsuda"},
    {name: "Private buckets", calories: "bkt0 bkt1 bkt3"},
    {name: "Public buckets", calories: ""},
    {name: "Public download buckets", calories: ""},
    {name: "Public upload buckets", calories: ""},
    {name: "Pool-ID", calories: "UFW3ZA6tYEQ2jqV3QmUU"},
    {name: "MinIO state", calories: "ready (reason: -)"},
    {name: "Expiration date", calories: "2043-05-01T07:18:24.000Z"},
    {name: "User enabled", calories: "true"},
    {name: "Pool online", calories: "true"},
    {name: "Creation date", calories: "2023-05-06T07:18:24.000Z"},
  ],

  pool_list: [
    {
      desserts: [
        {name: "Buckets directory", calories: "/home/users/m-matsuda/pool-a"},
        {name: "Unix user", calories: "m-matsuda"},
        {name: "Unix group", calories: "m-matsuda"},
        {name: "Private buckets", calories: "bkt0 bkt1 bkt3"},
        {name: "Public buckets", calories: ""},
        {name: "Public download buckets", calories: ""},
        {name: "Public upload buckets", calories: ""},
        {name: "Pool-ID", calories: "UFW3ZA6tYEQ2jqV3QmUU"},
        {name: "MinIO state", calories: "ready (reason: -)"},
        {name: "Expiration date", calories: "2043-05-01T07:18:24.000Z"},
        {name: "User enabled", calories: "true"},
        {name: "Pool online", calories: "true"},
        {name: "Creation date", calories: "2023-05-06T07:18:24.000Z"},
      ],
    },
  ],
};

export function api_list_pools() {
  const base_path = "";
  const msg = "list pools";
  const method = "GET";
  const path = (base_path + "/pool");
  const body = null;
  const triple = {method, path, body};
  return console.log(msg, triple, render_pool_list);
}
