# Models

Model weights are never committed to this repository. The setup step fetches them onto your machine, records the version and license of each in `models/manifest.json`, and the identify stage refuses to run against a model that is not listed there.

| Purpose | Default | License | Bring your own |
|---|---|---|---|
| Person detection (presence, person-area, group size) | **YOLOv8n**, exported to ONNX at setup | AGPL-3.0 (Ultralytics). It runs locally on your machine; the license governs the model, not this repository's MIT-licensed code, and the weights are not redistributed here | Set `[models] person_detector = "<path to your .onnx>"` in `project/config.toml`, with `input_size` and `class_index` for "person". Any detector that outputs boxes and scores works; Apache-2.0 choices include YOLOX-nano and NanoDet |
| Face detection (counts, largest face) | OpenCV Zoo YuNet, fetched at setup | permissive | `[models] face_detector = "<path>"` |
| Face recognition (the identity gate, later milestone) | An ArcFace-class model through onnxruntime | check before use | `[models] face_embedder = "<path>"` |

Everything runs on CPU through onnxruntime and OpenCV; nothing is uploaded anywhere. If you would rather not use an AGPL model at all, set the person detector to a permissively licensed ONNX file and the setup step will skip the YOLOv8n fetch.
