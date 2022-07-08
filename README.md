# OpenTimelineIO ShotGrid Library

A library to represent [OpenTimelineIO](http://opentimeline.io/) data in [ShotGrid](https://www.shotgrid.com),
and vice versa.

## Installation

Local installation for development:

```
pip install -e .[dev]
```

## sg-otio usage.
You can access the help with `sg-otio read --help` and `sg-otio write --help`. 

### sg-otio Shotgrid login information

You can provide Shotgrid login information in 3 different ways:
- `--login <username> --password <password>`
- `--script-name <script name> --api-key <api key>`
- `--session-token <session token>`

### sg-otio read
Read a Cut from SG and either output it in OTIO format or write it to a file. Any format suppported by OpenTimelineIO's standard adapters is supported.

Examples:
```
sg-otio read --sg-site-url URL --session-token TOKEN --cut-id CUT_ID
sg-otio read --sg-site-url URL --session-token TOKEN --cut-id CUT_ID --file output.otio
sg-otio read --sg-site-url URL --session-token TOKEN --cut-id CUT_ID --file output.xml --adapter-name fcp_xml
sg-otio read --settings SETTINGS.JSON --sg-site-url URL --session-token TOKEN --cut-id CUT_ID --file output.xml --adapter-name fcp_xml
```
### sg-otio write
Write a Video Track to SG as a Cut.
Example:
```
sg-otio write -u URL --session-token TOKEN --entity-type Cut --entity-id CUT_ID --file INPUT.edl --movie INPUT.mov --settings SETTINGS.JSON
```

### Settings file
Some settings for sg-otio read and write can be stored in a JSON file, and passed
to sg-otio with `--settings[-s] path/to/SETTINGS.JSON`.
This is what such file would contain with the default settings:
```json
{
  "default_head_in": 1001,
  "default_head_in_duration": 8,
  "default_tail_out_duration": 8,
  "use_clip_names_for_shot_names": false,
  "clip_name_shot_regexp": null,
  "local_storage_name": "primary",
  "versions_path_template": "{PROJECT}/{LINK}/{YYYY}{MM}{DD}/cuts",
  "version_names_template": null,
  "create_missing_versions": true,
  "timecode_in_to_frame_mapping_mode": 1,
  "timecode_in_to_frame_relative_mapping": ["00:00:00:01", 1001],
  "use_smart_fields": false,
  "shot_cut_fields_prefix": null
}
```
