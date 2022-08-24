SG Otio, an OpenTimelineIO ShotGrid Library
=======

[![Run tests](https://github.com/GPLgithub/sg-otio/actions/workflows/ci.yaml/badge.svg)](https://github.com/GPLgithub/sg-otio/actions/workflows/ci.yaml)

[![codecov](https://codecov.io/gh/GPLgithub/sg-otio/branch/master/graph/badge.svg?token=9X2MDPFCBI)](https://codecov.io/gh/GPLgithub/sg-otio)

A library to represent [OpenTimelineIO](http://opentimeline.io/) data in [ShotGrid](https://www.shotgrid.com),
and vice versa.

Disclaimer
----------

SG Otio is currently in Public Alpha. That means that it may be missing
some essential features and there are large changes planned. During this phase
we actively encourage you to provide feedback, requests, comments, and/or
contributions.


Installation
------------

### SG Python API

The SG Python API is not available on PyPi and must be manually installed
from github, e.g. `pip install git+https://github.com/shotgunsoftware/python-api.git`

### ffmpeg
sg-otio requires ffmpeg to be installed, and ffmpeg must be in the `PATH`.

- Binaries can be downloaded from [FFmpeg download page](https://ffmpeg.org/download.html), in which case the
binaries should be added to the `PATH` environment variable.
- A package manager can be used, for example on MacOS, `brew install ffmpeg`, in
which case the PATH should already be updated by the package manager.

### sg-otio package

SG Otio can be installed from PyPi, e.g. `pip install sg-otio`

SG Otio can also be installed from sources.
- Get a local copy of this repo: `git clone https://github.com/GPLgithub/sg-otio.git`
- Install it with `pip`: `pip install ./sg-otio`

sg-otio usage
-------------

You can access the help with `sg-otio read --help`, `sg-otio write --help`, or `sg-otio compare --help`. 

### ShotGrid login information

You can provide Shotgrid login information in 3 different ways:
- `--login <username> --password <password>`
- `--script-name <script name> --api-key <api key>`
- `--session-token <session token>`

### Reading a Cut from SG
Read a Cut from SG and either output it in OTIO format or write it to a file. Any format suppported by OpenTimelineIO's standard adapters is supported.

Examples:
```
sg-otio read --sg-site-url URL --session-token TOKEN --cut-id CUT_ID
sg-otio read --sg-site-url URL --session-token TOKEN --cut-id CUT_ID --file output.otio
sg-otio read --sg-site-url URL --session-token TOKEN --cut-id CUT_ID --file output.xml --adapter-name fcp_xml
sg-otio read --settings SETTINGS.JSON --sg-site-url URL --session-token TOKEN --cut-id CUT_ID --file output.xml --adapter-name fcp_xml
```

### Writing a Cut to SG
Write a Video Track to SG as a Cut.
Example:
```
sg-otio write -u URL --session-token TOKEN --entity-type Cut --entity-id CUT_ID --file INPUT.edl --movie INPUT.mov --settings SETTINGS.JSON
```

### Comparing a Video Track to a SG Cut
Read a Video Track from an OpenTimelinio source and compare it to an existing SG Cut.
Any format suppported by OpenTimelineIO's standard adapters is supported for the source.
The video Track can be written to SG as a new Cut by adding the `--write` argument.
The new SG Cut will be linked to the SG Entity the previous SG Cut is linked to.
Examples:
```
sg-otio compare --sg-site-url URL  --session-token TOKEN --file INPUT OTIO --cut-id CUT_ID
sg-otio compare --sg-site-url URL  --session-token TOKEN --file INPUT OTIO --cut-id CUT_ID --write
``` 

### Settings file

Some settings for sg-otio read and write can be stored in a JSON file, and passed
to sg-otio with `--settings[-s] path/to/SETTINGS.JSON`.
This is what such file would contain with the default settings:
```json
{
  "default_head_in": 1001,
  "default_head_duration": 8,
  "default_tail_duration": 8,
  "use_clip_names_for_shot_names": false,
  "clip_name_shot_regexp": null,
  "local_storage_name": "primary",
  "versions_path_template": "{PROJECT}/{LINK}/{YYYY}{MM}{DD}/cuts",
  "version_names_template": null,
  "create_missing_versions": true,
  "timecode_in_to_frame_mapping_mode": 1,
  "timecode_in_to_frame_relative_mapping": ["00:00:00:01", 1001],
  "use_smart_fields": false,
  "shot_cut_fields_prefix": null,
  "shot_omit_status": "omt",
  "shot_reinstate_status": "Previous Status",
  "reinstate_shot_if_status_is": ["omt", "hld"]
}
```

#### Default Head In, Default Head Duration, Default Tail Duration
When creating new Shots in ShotGrid, the values to use for the start frame and handles.

##### Use Clip Names for Shot Names
If set to True, the Clip name will be used as a Shot name if it can't be computed from
locators nor comments in the EDL.

##### Clip Name Shot Regexp
If set, use a regular expression to extract the Shot name from the Clip name.

#### Create Missing Versions
If set to True, for Clips with media references that don't have a version in ShotGrid,
a new version will be created in ShotGrid.

- For an EDL without media references, a movie of the Cut needs to be passed to sg-otio,
which will allow to extract the Versions from the Cut movie.
- For formats like Premiere XML, this means that media references existing in the XML
file will be published to ShotGrid.

#### Local storage name
When creating missing Versions, the SG local storage to use to publish the files to.

#### Versions Path Template
When creating missing Versions, the path to use to publish the files to.

This is a relative path from the local storage chosen.

The following keys are available:
`PROJECT, CUT_TITLE, LINK, HH, DD, MM, YY, YYYY`

Example valid templates:
- `{PROJECT}/{LINK}/{YYYY}{MM}{DD}/cuts (default)`
- `{PROJECT}/{CUT_TITLE}/{YYYY}{MM}{DD}/`

#### Version Names Template
If not specified, the Version name will be the Clip name.
If specified, the Version name will be computed using the template.

The following keys are available:
`CLIP_NAME, CUT_ITEM_NAME, SHOT, CLIP_INDEX, UUID`

The `CLIP_NAME` and `CUT_ITEM_NAME` are almost the same, but the `CUT_ITEM_NAME`
is guaranteed to be unique in a track.
For example, if there are two clips with the name `clip1`, their cut item names
will be `clip1` and `clip1_001`.

The `CLIP_INDEX` is the index of the clip in the track (starting from 1, and counting
only clips, not gaps or other elements).

The `UUID` is 6 digits long.

Even though versions with the same names are allowed, it is recommended to use keys that
guarantee the unicity of the names, like CUT_ITEM_NAME, CLIP_INDEX, or UUID.

Example valid templates:
- `{CLIP_NAME}_{UUID}` (default)
- `{CUT_ITEM_NAME}`
- `{SHOT}_{CLIP_INDEX}`
- `{CLIP_NAME}_{CLIP_INDEX:04d}` (adds some leading zeros)

#### Timecode In to Frame Mapping Mode
Different timecode in values to frame mapping modes

Three mapping modes are available, which are only relevant for straight
imports (without comparing to a previous Cut):
- `0`: Absolute. Timecode in is mapped to the Shot head in.
- `1`: Automatic. Timecode is converted to an absolute frame number.
- `2`: Relative. timecode in is converted to an arbitrary frame
number specified through settings. Example: `["00:00:00:01", 1001]`

#### Timecode In to Frame Relative Mapping.
If the Timecode In to Frame Mapping Mode is set to `2`, this setting can be used to specify
how to convert the timecode to an arbitrary frame number.

#### Use Smart Fields
If set to True, the Smart Cut Fields will be used to fill the Shot fields.

#### Shot Cut Fields Prefix
If set, the Shot Cut Fields will be custom fields that use this prefix,
e.g. `sg_PREFIX_cut_in`, `sg_PREFIX_cut_out`, etc.


#### Omitting and Reinstating Shots
If some Shots are omitted from one Cut to the other, their Status will be set
to the `shot_omit_status` setting value.
Shots which appear again in a Cut will be reinstated if their current status 
is one of the statuses set with the `reinstate_shot_if_status_is` setting.
Their status will be set to the value set with the `shot_reinstate_status` setting, 
unless it is the special "Previous Status" value. In this case the status they
had before being omitted will be set.

License
-------
SG Otio is open source software. Please see the [LICENSE.txt](LICENSE.txt) for details.
