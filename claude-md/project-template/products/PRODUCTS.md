# Products

Large files made by project scripts. They are not input data (`data/` is never edited) and not run outputs (`outputs/` is tracked and limited by the file guard of the run control script). The folder `products/` is git-ignored except this register, so git does not hold the files: **keep a copy outside this machine**.

## Rule

A file goes in `products/` if a project script makes it and one of these holds:
1. it is over the file limit of the file guard of the run control script, or it is a video or an animation of any size;
2. it is an intermediate that a later script reads and git need not hold.

Anything that the file guard would block in `outputs/` goes here. A figure or table that supports a report stays in `outputs/`, within the guard limits.
Downloaded or supplied files are not products: they go in `sources/` (`data/` is not touched).

Every file in `products/` has one row below with its script and run tag. `check_records.py` flags a listed file that is missing. A script that makes a large file writes it here, or takes this folder as its scratch argument. A script that writes a video to its outputs folder: move the video here after the run.

State here whether the scripts regenerate each file byte for byte (videos usually do not: rerun the script of the run tag). Give the sha256 as the first 12 characters and the date it was taken.

Describe the layout of any raw binary grid below the table (dimensions, data type, order, no-data value).

| File | Content | Size (MB) | Script | Run tag | sha256 |
|---|---|---|---|---|---|
