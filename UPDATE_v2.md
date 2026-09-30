# Update v2 (2026-09-30)

Why: the IROS 2025 version of the paper links the authors' public release
(https://github.com/CKL9001/SDA-LLM) with the VisDial dataset and notebooks. v2 adds
"Track V" to re-run that data first, before the ARKitScenes track.

Files in this update (copy over the repo, same paths):
- NEW  src/sdarepro/visdial.py      loader for the authors' release (Type A Office, Type B counts)
- NEW  scripts/fetch_visdial.sh     clones the release into third_party/ (never commit it)
- NEW  scripts/run_visdial.py       runs Track V (V1 Type A four conditions, V2 Type B counts)
- CHG  src/sdarepro/prompts.py      full authors' instruction text, tag-agnostic wording, SYSTEM_COUNT
- CHG  src/sdarepro/vlm.py          ids_from() also accepts drawn name tags like "chair 3"
- CHG  src/sdarepro/scene.py        Object3D.tag (optional drawn tag text)
- CHG  src/sdarepro/annotate.py     custom tag text, tags no longer cover each other
- CHG  src/sdarepro/prepare.py      PreparedScene.name_map
- CHG  src/sdarepro/runner.py       passes name_map, adds run_count_dialogue()
- CHG  tests/test_core.py           +3 tests (20 total; 2 need the release cloned)
- CHG  PLAN.md                      v2: section 3.0 (release + data issues), 5.0 Track V, milestone M0.5
- CHG  README.md, CLAUDE.md, .gitignore

This update was merged into the repo directly on 2026-09-30 by the Cowork session, on top of the M1 fixes
(up axis, image rotation, normalizedAxes rows). Those fixes were kept; v2 only adds the items above.
The tag-overlap problem noted in M1 (#29/#30 in view 0) is handled by the new tag placement in annotate.py.

Check: `bash scripts/fetch_visdial.sh && pytest -q` should show 30 passed (the ARKitScenes real-data test runs
only where data/ exists).
