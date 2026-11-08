# Output index

This file lives at `outputs/INDEX.md` in the project root and is tracked in git. There is one line per accepted or rejected run, in the order the runs were made. Each run is an annotated git tag `<task>-<DDMMYY>-run<N>` on the commit that holds its outputs in the task folder `outputs/<task>/`. `run_control.py accept` and `reject` add the lines and mark the superseded run; edit a status by hand only when later work changes what a run means. Status is current, superseded or not adopted (tag suffix `-rejected`).

| Run (tag or legacy folder) | Task folder | Question answered | Status | Superseded by |
|---|---|---|---|---|
