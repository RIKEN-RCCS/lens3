User's Manual of Lenticularis
==========================================================

# Registration

  + Overview
    - To Start Using
      - Register Zones with WebUI
        - Access Key IDs for Zone are generated by the system.
        - Access Key consists of Access Key ID and Secret Access Key.
        - The system generates three Access Keys, for readwrite, for readonly, 
          and for writeonly.
        - Zone holds all parameters of itself, such as "directory (storage) 
          for buckets"
        - Once Zone is registers, it will be activated immediately.
      - Access to the Endpoint URL with given Access Key
        - Two types of Endpoint URL is available:
          1. Host part of the Endpoint URL is shared by all users (delegate 
          hostname)
          2. Host part of the Endpoint URL is direct hostname, that is 
          dedicated domain name for the zone.
        - Use Path-Style addressing to specify bucket.
    - To Stop Using (inactivate registered zones)
      - Delete Zones with WebUI

  + Registration Procedure
    1. Obtain access information to the WebUI from the system administrator.
       (assume `https://console.lent8.example.com/` in this example)
    2. In figure 1, shows the initial screen of 
       `https://console.lent8.example.com/`, no zone is registered here.
    3. To start creating a new zone, click "New Entry" button (figure 2).
      - Fill zone information.
      - Allowed maximum number of zones per user is limited by system settings.
        - In case you exceeds the limit, you'll get following message: 
          "You are not allowed to create more than # Zone(s)."
      - The following parameters must set by user:
        - Group: group id that used to run MinIO. 
        - Buckets Directory: directory used for storing buckets.
          - Buckets directory must unique all over the system.
            (no two zones share same Buckets Directory)
          - Two directories that are in ancestor-descendant relationship 
            are allowed
          - The system does not system-wide (public) Buckets Directory.
            Buckets directory should created under user's home directory.
        - Expiration DateTime: specify date in UTC.  default is set by system.
          - Service is cycled, when changed expiration date, including
            expiration date is prolonged. 
        - Status: Zone' status (default: Online)
          - Choice: Online, Offline
        - Direct Hostname: assign direct hostname for direct access service.
          - All access to Endpoint URL which host part is Direct Hostname
            is redirected to corresponding zone to that direct hostname.
            On access using direct hostname,  Access Key ID is required,
            unless the bucket of the zone is made public.
          - Case insensitive.
      - Access Key ID and Secret Access Key are generated automatically.
        - Users cannot specify Access Key ID and Secret Access Key on 
          first hand.  In case the generated keys are ominous, use Change 
          Access Key button to re-generate them.
      - Click Create/Update button to launch the zone.
        Click Delete button to delete the Zone.
        - On launching zone, it took several seconds to initialize zone.
        - On initialization failure, error message will displayed.
    4. Figure 3 shows the display after creating some zones.
       on this screen, click Edit to edit the zone and click Delete
       to delete the zone.

  + Figures
    - Figures of WebUI

      ```
      +-------------------------------------------------------------------------+
      | [New Entry]                                                             |
      +-------------------------------------------------------------------------+
      ```

    - Figure 1 List Entries (initial)


      ```
      +-------------------------------------------------------------------------+
      | User:                a00000                                             |
      | Group:             [ rccs-aot                                         ] |
      |                                                                         |
      | Access Key for Read/Write User:                                         |
      | Access Key ID:       WoRKvRhrdaMNSlkZcJCB                               |
      | Secret Access Key:   DzZv57R8wBIuVZdtAkE1uK1HoebLPMzKM6obA4IDqOhaLIBf   |
      |                                                                         |
      | Access Key for Read Only User:                                          |
      | Access Key ID:       SeCOnDarY1suxaPre0CC                               |
      | Secret Access Key:   SB9ujG2VAdhXcyunHqXZv7tZwVm5wX76ptR7L0FvF5cYFoto   |
      |                                                                         |
      | Access Key for Write Only User:                                         |
      | Access Key ID:       rY1suSeCOnDaxaPre0CC                               |
      | Secret Access Key:   5cYFotoSB9ujG2VAdhXcyunHqXZv7tZwVm5wX76ptR7L0FvF   |
      |                                                                         |
      | Buckets Directory: [ /vol0000/rccs-aot/a00000/work                    ] |
      | * this field is editable on creating zone stage                         |
      |   i.e. cannot modify created zone's buckets directory                   |
      |  (data direcotry)                                                       |
      |                                                                         |
      | Buckets:                                                                |
      | Plubic:   [public1, public2, ...                                      ] |
      | Download: [downloadonly1, downloadonly2, ...                          ] |
      | Upload:   [uploadonly1, uploadonly2, ...                              ] |
      |                                                                         |
      | Direct Hostname:   [                   ] .lent8.example.com             |
      |  (case insensitive)                                                     |
      |                                                                         |
      | Expiration DateTime: [ 2022-01-01 00:00:00 UTC                        ] |
      | * modifiable any time                                                   |
      | Status:            [*] Online   [ ] Offline                             |
      | * modifiable any time                                                   |
      |                                                                         |
      | [Create]/[Update]                                                       |
      +-------------------------------------------------------------------------+
      ```

    - Figure 2 Entry Editing Pane

      ```
      +-------------------------------------------------------------------------+
      | User:                a00000                                             |
      | Group:               rccs-aot                                           |
      |                                                                         |
      | Access Key for Read/Write:                                              |
      | Access Key ID:       WoRKvRhrdaMNSlkZcJCB                               |
      | Secret Access Key:   DzZv57R8wBIuVZdtAkE1uK1HoebLPMzKM6obA4IDqOhaLIBf   |
      |                                                                         |
      | Access Key for Read Only:                                               |
      | Access Key ID:    SeCOnDarY1suxaPre0CC                                  |
      | Secret Access Key:SB9ujG2VAdhXcyunHqXZv7tZwVm5wX76ptR7L0FvF5cYFoto      |
      |                                                                         |
      | Access Key for Write Only User:                                         |
      | Access Key ID:       rY1suSeCOnDaxaPre0CC                               |
      | Secret Access Key:   5cYFotoSB9ujG2VAdhXcyunHqXZv7tZwVm5wX76ptR7L0FvF   |
      |                                                                         |
      | Endpoint URL(s):     https://lent8.example.com/                         |
      |                                                                         |
      | Direct Hostname:                                                        |
      | Buckets Directory:   /vol0000/rccs-aot/a00000/work                      |
      | Expiration DateTime: 2022-01-01 00:00:00 UTC                            |
      | Status:              Online                                             |
      | Last Access:         2021-08-25 12:25:34 UTC                            |
      |                                                                         |
      | [Edit] [Delete]                                                         |
      +-------------------------------------------------------------------------+
      | User:                a00000                                             |
      | Group:               rccs-aot                                           |
      |                                                                         |
      | Access Key for Read/Write:                                              |
      | Access Key ID:       RE1easekSHlxQzJDrTxu                               |
      | Secret Access Key:   RmvJ5RmDavIWSiDNoCICnfQKIouwjlJGIa9cQ9PvYTthgQMp   |
      |                                                                         |
      | Access Key for Read Only:                                               |
      | Access Key ID(R):    slBGY39FX1Y8IeIgSBMA                               |
      | Secret Access Key(R):Q0stpMxzNkMl6AEvuNoihBOTyo2SS2oSBYVrmAxeQJFf3whY   |
      |                                                                         |
      | Access Key for Write Only:                                              |
      | Access Key ID(R):    9FX1Y8IeIgSBMAslBGY3                               |
      | Secret Access Key(R):kMl6AEvuNoihBOTyo2SS2oSBYVrmAxeQJFf3whYQ0stpMxzN   |
      |                                                                         |
      | Endpoint URL(s):     https://lent8.example.com/                         |
      |                      https://a0release.lent8.example.com/               |
      | Buckets Directory:   /vol0000/rccs-aot/a00000/release                   |
      | Expiration DateTime: Unlimited                                          |
      | Status:              Offline                                            |
      | Last Access:         Never                                              |
      |                                                                         |
      | [Edit] [Delete]                                                         |
      +-------------------------------------------------------------------------+
      | [New Entry]                                                             |
      +-------------------------------------------------------------------------+
      ```

    - Figure 3 List Entries (after registration)

  + Note:

    - In case Buckets Directory does not exist:
      - If specified Buckets Directory does not exist MinIO will automatically
        generates it.
        - If parent directory (or ancestor directory) of the directory is 
          not writable by the user, its error.

    - Users that disabled by system administrator cannot edit zone.
      - Including cannot modify or delete existing entries.
      - Once the user is re-enabled by the administrator, the user's zone
        also enabled.

    - MinIO's behavior on Zone creation
      - MinIO is initiated temporarily to initialize zone, even if
        the created zone marked Offline or already expired at the creation time.

    - Deleting Zone
      - Even if a zone is deleted, buckets directory and all objects stored
        in the directory keep left.
      - If buckets directory of deleted zone is reused another zone,
        - All existing bucket's policy is set to none, allowing 
          only users that have access key to access the bucket.

    - Changing Status
      - Changing status to offline stops service immediately.
      - Cycling status (Online -> Offline -> Online) does not
        affect bucket's policy.

    - On expiration
      - On expiration, the service of the zone stopped immediately.
      - All zone's settings remained online.
        - Prolonging expiration date will make zone available again.
      - WebUI doesn't warn the zone is expired even if the zone
        is already expired at creation time.

    - Restriction of Direct Hostname
      - Only one direct hostname can be assigned to a zone.
      - Domain name length must be between 3 to 64 characters.
      - Direct hostname syntax may be restricted by the administrator
          - Direct hostname cannot contain "."

  + CLI
    - The system does not provide CLI for users.


# Client Settings (example)

  + Access to Endpoint URL with Access Key (Access Key ID and Secret 
    Access Key) provided by the WebUI.

    ```
    $ cat .aws/credentials
    [user1]
    aws_access_key_id = WoRKvRhrdaMNSlkZcJCB
    aws_secret_access_key = DzZv57R8wBIuVZdtAkE1uK1HoebLPMzKM6obA4IDqOhaLIBf

    $ ENDPOINT_URL=http://lent8.example.com/
    $ aws --endpoint-url=$ENDPOINT_URL s3 ls s3://wrk-bucket1/
    ```

[eof]