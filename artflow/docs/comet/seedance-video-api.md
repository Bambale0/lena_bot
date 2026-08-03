> ## Documentation Index
> Fetch the complete documentation index at: https://apidoc.cometapi.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Create a Seedance video

> Create a Seedance video task on CometAPI. Use text prompts or reference images, select a duration, and request an exact WxH output size.

<Info>
  Choose a documented `WxH` value from the table below for the `size` field.
</Info>

<Warning>
  Use `doubao-seedance-2-0-mini` exactly for Seedance 2.0 Mini.
  The shortened `seedance-mini` value is not a valid model ID.
</Warning>

## Supported model IDs

Use one of these exact values for the `model` field.

| Model             | Exact model ID             | Modes and resolution tiers                                   | Supported `seconds` |
| ----------------- | -------------------------- | ------------------------------------------------------------ | ------------------- |
| Seedance 2.0      | `doubao-seedance-2-0`      | Text-to-video, image-to-video; `480p`, `720p`, `1080p`, `4K` | `4`-`15`            |
| Seedance 2.0 Fast | `doubao-seedance-2-0-fast` | Text-to-video, image-to-video; `480p`, `720p`                | `4`-`15`            |
| Seedance 2.0 Mini | `doubao-seedance-2-0-mini` | Text-to-video, image-to-video; `480p`, `720p`                | `4`-`15`            |
| Seedance 1.5 Pro  | `doubao-seedance-1-5-pro`  | Text-to-video; `480p`, `720p`, `1080p`                       | `4`-`12`            |
| Seedance 1.0 Pro  | `doubao-seedance-1-0-pro`  | Text-to-video; `480p`, `720p`, `1080p`                       | `2`-`10`            |

## Use reference images

Seedance 2.0, Seedance 2.0 Fast, and Seedance 2.0 Mini accept
`input_reference`. For advanced multi-reference prompts on a route that
supports them, repeat the same multipart field in upload order.

One Mini production request with a single `input_reference` completed at
`720x1280`. That check confirmed request completion, but it did not isolate the
reference image's visual effect from the prompt.

Seedance 2.0 is sensitive to how the prompt connects each reference image to the scene. Refer to the uploaded files by order, such as `[Image 1]`, `[Image 2]`, and `[Image 3]`, then assign each image a clear role:

* Use `[Image 1]` for the main subject, character, or product.
* Use `[Image 2]` for a secondary subject, prop, or companion.
* Use `[Image 3]` for the background, setting, lighting, or style.

Describe what should stay recognizable, what can change, the action, camera motion, visual style, and scene. A vague prompt can make the generated video look like the reference image was not used, even when the upload was accepted.

This prompt structure is more reliable than only listing images:

```text theme={null}
Use the uploaded images in order: keep the boy wearing glasses and a blue T-shirt from [Image 1], add the corgi puppy from [Image 2], and use the lawn from [Image 3] as the setting. Create a 4-second 3D cartoon video with the boy and puppy sitting together, a slow camera push-in, soft daylight, and no extra characters.
```

## Duration by model

If you omit `seconds`, CometAPI requests a 5-second clip. Send `seconds` as a
string when you need a specific duration.

| Model family                                           | Supported `seconds` | Default | Boundary behavior             |
| ------------------------------------------------------ | ------------------- | ------- | ----------------------------- |
| Seedance 2.0, Seedance 2.0 Fast, and Seedance 2.0 Mini | `4`-`15`            | `5`     | Use integer seconds in range. |
| Seedance 1.5 Pro                                       | `4`-`12`            | `5`     | Use integer seconds in range. |
| Seedance 1.0 Pro                                       | `2`-`10`            | `5`     | Use integer seconds in range. |

## Size support by model

The table below keeps the exact `WxH` values in one place. Seedance 2.0 Fast
uses only the `480p` and `720p` values in the fifth column. The `1080p` values
in that column apply to Seedance 1.5 Pro and standard Seedance 2.0. The `4K`
values apply only to standard Seedance 2.0. In the Mini column, `—` means the
resolution is not supported.

| Resolution class | Aspect ratio | Seedance 2.0 Mini | Seedance 1.0 series | Seedance 1.5 Pro / standard Seedance 2.0 / Fast |
| ---------------- | ------------ | ----------------- | ------------------- | ----------------------------------------------- |
| `480p`           | `16:9`       | `864x496`         | `864x480`           | `864x496`                                       |
|                  | `4:3`        | `752x560`         | `736x544`           | `752x560`                                       |
|                  | `1:1`        | `640x640`         | `640x640`           | `640x640`                                       |
|                  | `3:4`        | `560x752`         | `544x736`           | `560x752`                                       |
|                  | `9:16`       | `496x864`         | `480x864`           | `496x864`                                       |
|                  | `21:9`       | `992x432`         | `960x416`           | `992x432`                                       |
| `720p`           | `16:9`       | `1280x720`        | `1248x704`          | `1280x720`                                      |
|                  | `4:3`        | `1112x834`        | `1120x832`          | `1112x834`                                      |
|                  | `1:1`        | `960x960`         | `960x960`           | `960x960`                                       |
|                  | `3:4`        | `834x1112`        | `832x1120`          | `834x1112`                                      |
|                  | `9:16`       | `720x1280`        | `704x1248`          | `720x1280`                                      |
|                  | `21:9`       | `1470x630`        | `1504x640`          | `1470x630`                                      |
| `1080p`          | `16:9`       | —                 | `1920x1088`         | `1920x1080`                                     |
|                  | `4:3`        | —                 | `1664x1248`         | `1664x1248`                                     |
|                  | `1:1`        | —                 | `1440x1440`         | `1440x1440`                                     |
|                  | `3:4`        | —                 | `1248x1664`         | `1248x1664`                                     |
|                  | `9:16`       | —                 | `1088x1920`         | `1080x1920`                                     |
|                  | `21:9`       | —                 | `2176x928`          | `2206x946`                                      |
| `4K`             | `16:9`       | —                 | —                   | `3840x2160` (Seedance 2.0 only)                 |
|                  | `4:3`        | —                 | —                   | `3326x2494` (Seedance 2.0 only)                 |
|                  | `1:1`        | —                 | —                   | `2880x2880` (Seedance 2.0 only)                 |
|                  | `3:4`        | —                 | —                   | `2494x3326` (Seedance 2.0 only)                 |
|                  | `9:16`       | —                 | —                   | `2160x3840` (Seedance 2.0 only)                 |
|                  | `21:9`       | —                 | —                   | `4398x1886` (Seedance 2.0 only)                 |

<Warning>
  Seedance 2.0 Mini supports `480p` and `720p`, not `1080p` or `4K`.
  In one production check, a Mini request for `1920x1080` produced
  `1280x720`.
</Warning>

Choose the documented `WxH` value for the target model. Exact `WxH` support remains model-dependent, so inspect the completed media before relying on an undocumented size.


## OpenAPI

````yaml api/openapi/video/seedance/post-seedance-create.openapi.json POST /v1/videos
openapi: 3.1.0
info:
  title: Seedance Video Generation API
  version: 1.0.0
  description: >-
    Create an asynchronous ByteDance Seedance video task through CometAPI. Use
    one of the five documented model IDs exactly. Seedance 2.0 Mini supports the
    documented 480p and 720p WxH values, but not 1080p or 4K. Save the returned
    id and poll GET /v1/videos/{id} until the status reaches completed.
servers:
  - url: https://api.cometapi.com
security:
  - bearerAuth: []
paths:
  /v1/videos:
    post:
      summary: Create a Seedance video task
      description: >-
        Submit a Seedance video task as multipart/form-data. Seedance 2.0,
        Seedance 2.0 Fast, and Seedance 2.0 Mini accept input_reference;
        Seedance 1.0 Pro and 1.5 Pro accept text prompts only. For multiple
        reference images on a route that supports them, repeat input_reference
        in upload order and describe each image's role in the prompt. The
        endpoint returns a task id; use GET /v1/videos/{id} to read the final
        result.
      operationId: seedance_create_video
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              type: object
              required:
                - prompt
                - model
              properties:
                prompt:
                  type: string
                  description: >-
                    Text prompt that describes the video. Required. When using
                    reference images, describe what each uploaded image should
                    control, such as the subject from [Image 1], the secondary
                    object from [Image 2], and the background or style from
                    [Image 3]. Also state the action, camera motion, visual
                    style, and scene.
                  example: >-
                    A slow cinematic camera push across a coastal landscape at
                    sunrise.
                model:
                  type: string
                  description: >-
                    Seedance model ID. Use one of the exact values below.
                    Aliases such as seedance-mini are not accepted.
                  enum:
                    - doubao-seedance-2-0
                    - doubao-seedance-2-0-fast
                    - doubao-seedance-2-0-mini
                    - doubao-seedance-1-5-pro
                    - doubao-seedance-1-0-pro
                  example: doubao-seedance-2-0-mini
                seconds:
                  type: integer
                  description: >-
                    Video duration in seconds. Seedance 2.0, Seedance 2.0 Fast,
                    and Seedance 2.0 Mini accept 4 to 15. Seedance 1.5 Pro
                    accepts 4 to 12, and Seedance 1.0 Pro accepts 2 to 10. The
                    default is 5.
                  minimum: 2
                  maximum: 15
                  default: 5
                  example: 5
                size:
                  type: string
                  description: >-
                    Output size as an exact WxH value. For Seedance 2.0 Mini,
                    use 864x496, 752x560, 640x640, 560x752, 496x864, or 992x432
                    for 480p; use 1280x720, 1112x834, 960x960, 834x1112,
                    720x1280, or 1470x630 for 720p. Mini does not support 1080p
                    or 4K. A Mini request for 1920x1080 produced 1280x720 in one
                    production check. The standard Seedance 2.0 model also
                    accepts its documented 4K values.
                  pattern: ^[1-9]\d{2,3}x[1-9]\d{2,3}$
                  examples:
                    - 864x496
                    - 752x560
                    - 640x640
                    - 560x752
                    - 496x864
                    - 992x432
                    - 1280x720
                    - 1112x834
                    - 960x960
                    - 834x1112
                    - 720x1280
                    - 1470x630
                    - 1920x1080
                    - 1080x1920
                    - 3840x2160
                    - 3326x2494
                    - 2880x2880
                    - 2494x3326
                    - 2160x3840
                    - 4398x1886
                  example: 1280x720
                input_reference:
                  type: string
                  format: binary
                  description: >-
                    Optional reference image uploaded as a multipart file.
                    Seedance 2.0, Seedance 2.0 Fast, and Seedance 2.0 Mini
                    accept this field. On routes that support multiple reference
                    images, repeat the field and reference the files in upload
                    order as [Image 1], [Image 2], and so on. Seedance 1.0 Pro
                    and 1.5 Pro do not accept it.
            encoding:
              input_reference:
                contentType: image/jpeg, image/png, image/webp
            examples:
              seedance_2_0_mini_text_to_video:
                summary: Seedance 2.0 Mini text-to-video
                value:
                  prompt: >-
                    A matte red cube rotates slowly on a clean white studio
                    floor. The camera remains fixed. Soft daylight and a short
                    shadow.
                  model: doubao-seedance-2-0-mini
                  seconds: 15
                  size: 1280x720
      responses:
        '200':
          description: Task created. Save the returned id and poll GET /v1/videos/{id}.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/CreateVideoResponse'
              example:
                id: task_abc123
                task_id: task_abc123
                object: video
                model: doubao-seedance-2-0-mini
                status: queued
                progress: 0
                created_at: 1776681149
        '400':
          description: >-
            The request is missing a required field or contains an out-of-range
            value.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
              examples:
                missing_prompt:
                  summary: prompt field missing
                  value:
                    code: invalid_request
                    message: prompt is required
                missing_model:
                  summary: model field missing
                  value:
                    error:
                      code: ''
                      message: model name is required
                      type: comet_api_error
                invalid_duration:
                  summary: seconds outside the per-model range
                  value:
                    code: InvalidParameter
                    message: >-
                      the parameter duration specified in the request is not
                      valid
                i2v_not_supported:
                  summary: input_reference sent with a 1.0 Pro or 1.5 Pro model
                  value:
                    code: InvalidParameter
                    message: >-
                      The parameter task_type specified in the request is not
                      valid: the specified task_type r2v does not support model
                      seedance-1-5-pro
        '401':
          description: The API key is missing or invalid.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
              examples:
                invalid_token:
                  summary: Bearer token rejected
                  value:
                    error:
                      code: ''
                      message: invalid token
                      type: comet_api_error
      x-codeSamples:
        - lang: Shell
          label: Text-to-video (Seedance 2.0 Mini, exact 1280x720)
          source: |-
            curl https://api.cometapi.com/v1/videos \
              -H "Authorization: Bearer $COMETAPI_KEY" \
              -F 'prompt="A matte red cube rotates slowly on a clean white studio floor. The camera remains fixed. Soft daylight and a short shadow."' \
              -F 'model="doubao-seedance-2-0-mini"' \
              -F 'seconds="15"' \
              -F 'size="1280x720"'
        - lang: Python
          label: Text-to-video (Seedance 2.0 Mini, exact 1280x720)
          source: |
            import os
            import requests

            response = requests.post(
                "https://api.cometapi.com/v1/videos",
                headers={"Authorization": "Bearer " + os.environ["COMETAPI_KEY"]},
                data={
                    "prompt": "A matte red cube rotates slowly on a clean white studio floor. The camera remains fixed. Soft daylight and a short shadow.",
                    "model": "doubao-seedance-2-0-mini",
                    "seconds": "15",
                    "size": "1280x720",
                },
                timeout=30,
            )

            response.raise_for_status()
            print(response.json())
        - lang: JavaScript
          label: Text-to-video (Seedance 2.0 Mini, exact 1280x720)
          source: >
            const form = new FormData();

            form.append("prompt", "A matte red cube rotates slowly on a clean
            white studio floor. The camera remains fixed. Soft daylight and a
            short shadow.");

            form.append("model", "doubao-seedance-2-0-mini");

            form.append("seconds", "15");

            form.append("size", "1280x720");


            const response = await fetch("https://api.cometapi.com/v1/videos", {
              method: "POST",
              headers: { Authorization: `Bearer ${process.env.COMETAPI_KEY}` },
              body: form,
            });


            const result = await response.json();

            console.log(result);
        - lang: Shell
          label: Single reference image (Seedance 2.0)
          source: |-
            curl https://api.cometapi.com/v1/videos \
              -H "Authorization: Bearer $COMETAPI_KEY" \
              -F 'prompt="Use [Image 1] as the main visual reference. Preserve the subject identity, clothing colors, and overall composition from [Image 1]. Create a 4-second video with a gentle camera push-in, subtle natural motion, warm daylight, and a realistic cinematic style."' \
              -F 'model="doubao-seedance-2-0"' \
              -F 'seconds="4"' \
              -F 'size="720x1280"' \
              -F 'input_reference=@"/path/to/reference.png"'
        - lang: Python
          label: Single reference image (Seedance 2.0)
          source: >
            import os

            import requests


            prompt = "Use [Image 1] as the main visual reference. Preserve the
            subject identity, clothing colors, and overall composition from
            [Image 1]. Create a 4-second video with a gentle camera push-in,
            subtle natural motion, warm daylight, and a realistic cinematic
            style."


            with open("/path/to/reference.png", "rb") as image:
                response = requests.post(
                    "https://api.cometapi.com/v1/videos",
                    headers={"Authorization": "Bearer " + os.environ["COMETAPI_KEY"]},
                    data={
                        "prompt": prompt,
                        "model": "doubao-seedance-2-0",
                        "seconds": "4",
                        "size": "720x1280",
                    },
                    files=[("input_reference", ("reference.png", image, "image/png"))],
                    timeout=30,
                )

            response.raise_for_status()

            print(response.json())
        - lang: JavaScript
          label: Single reference image (Seedance 2.0)
          source: >
            import { readFile } from "node:fs/promises";


            const prompt = "Use [Image 1] as the main visual reference. Preserve
            the subject identity, clothing colors, and overall composition from
            [Image 1]. Create a 4-second video with a gentle camera push-in,
            subtle natural motion, warm daylight, and a realistic cinematic
            style.";

            const image = await readFile("/path/to/reference.png");


            const form = new FormData();

            form.append("prompt", prompt);

            form.append("model", "doubao-seedance-2-0");

            form.append("seconds", "4");

            form.append("size", "720x1280");

            form.append("input_reference", new Blob([image], { type: "image/png"
            }), "reference.png");


            const response = await fetch("https://api.cometapi.com/v1/videos", {
              method: "POST",
              headers: { Authorization: `Bearer ${process.env.COMETAPI_KEY}` },
              body: form,
            });


            const result = await response.json();

            console.log(result);
        - lang: Shell
          label: Multiple reference images (Seedance 2.0)
          source: |-
            curl https://api.cometapi.com/v1/videos \
              -H "Authorization: Bearer $COMETAPI_KEY" \
              -F 'prompt="Use the uploaded images in order: keep the boy wearing glasses and a blue T-shirt from [Image 1], add the corgi puppy from [Image 2], and use the lawn from [Image 3] as the setting. Create a 4-second 3D cartoon video with the boy and puppy sitting together, a slow camera push-in, soft daylight, and no extra characters."' \
              -F 'model="doubao-seedance-2-0"' \
              -F 'seconds="4"' \
              -F 'size="720x1280"' \
              -F 'input_reference=@"/path/to/seelite_ref_1.png"' \
              -F 'input_reference=@"/path/to/seelite_ref_2.png"' \
              -F 'input_reference=@"/path/to/seelite_ref_3.png"'
        - lang: Python
          label: Multiple reference images (Seedance 2.0)
          source: >
            import os

            import requests


            prompt = "Use the uploaded images in order: keep the boy wearing
            glasses and a blue T-shirt from [Image 1], add the corgi puppy from
            [Image 2], and use the lawn from [Image 3] as the setting. Create a
            4-second 3D cartoon video with the boy and puppy sitting together, a
            slow camera push-in, soft daylight, and no extra characters."


            with open("/path/to/seelite_ref_1.png", "rb") as image_1,
            open("/path/to/seelite_ref_2.png", "rb") as image_2,
            open("/path/to/seelite_ref_3.png", "rb") as image_3:
                response = requests.post(
                    "https://api.cometapi.com/v1/videos",
                    headers={"Authorization": "Bearer " + os.environ["COMETAPI_KEY"]},
                    data={
                        "prompt": prompt,
                        "model": "doubao-seedance-2-0",
                        "seconds": "4",
                        "size": "720x1280",
                    },
                    files=[
                        ("input_reference", ("seelite_ref_1.png", image_1, "image/png")),
                        ("input_reference", ("seelite_ref_2.png", image_2, "image/png")),
                        ("input_reference", ("seelite_ref_3.png", image_3, "image/png")),
                    ],
                    timeout=30,
                )

            response.raise_for_status()

            print(response.json())
        - lang: JavaScript
          label: Multiple reference images (Seedance 2.0)
          source: >
            import { readFile } from "node:fs/promises";


            const prompt = "Use the uploaded images in order: keep the boy
            wearing glasses and a blue T-shirt from [Image 1], add the corgi
            puppy from [Image 2], and use the lawn from [Image 3] as the
            setting. Create a 4-second 3D cartoon video with the boy and puppy
            sitting together, a slow camera push-in, soft daylight, and no extra
            characters.";

            const image1 = await readFile("/path/to/seelite_ref_1.png");

            const image2 = await readFile("/path/to/seelite_ref_2.png");

            const image3 = await readFile("/path/to/seelite_ref_3.png");


            const form = new FormData();

            form.append("prompt", prompt);

            form.append("model", "doubao-seedance-2-0");

            form.append("seconds", "4");

            form.append("size", "720x1280");

            form.append("input_reference", new Blob([image1], { type:
            "image/png" }), "seelite_ref_1.png");

            form.append("input_reference", new Blob([image2], { type:
            "image/png" }), "seelite_ref_2.png");

            form.append("input_reference", new Blob([image3], { type:
            "image/png" }), "seelite_ref_3.png");


            const response = await fetch("https://api.cometapi.com/v1/videos", {
              method: "POST",
              headers: { Authorization: `Bearer ${process.env.COMETAPI_KEY}` },
              body: form,
            });


            const result = await response.json();

            console.log(result);
        - lang: Shell
          label: Text-to-video (exact 1920x1080)
          source: |-
            curl https://api.cometapi.com/v1/videos \
              -H "Authorization: Bearer $COMETAPI_KEY" \
              -F 'prompt="A slow cinematic camera push across a coastal landscape at sunrise"' \
              -F 'model="doubao-seedance-1-5-pro"' \
              -F 'seconds="4"' \
              -F 'size="1920x1080"'
        - lang: Python
          label: Text-to-video (exact 1920x1080)
          source: |
            import os
            import requests

            response = requests.post(
                "https://api.cometapi.com/v1/videos",
                headers={"Authorization": "Bearer " + os.environ["COMETAPI_KEY"]},
                data={
                    "prompt": "A slow cinematic camera push across a coastal landscape at sunrise",
                    "model": "doubao-seedance-2-0",
                    "seconds": "4",
                    "size": "1920x1080",
                },
                timeout=30,
            )

            response.raise_for_status()
            print(response.json())
        - lang: JavaScript
          label: Text-to-video (exact 1920x1080)
          source: >
            const form = new FormData();

            form.append("prompt", "A slow cinematic camera push across a coastal
            landscape at sunrise");

            form.append("model", "doubao-seedance-1-5-pro");

            form.append("seconds", "4");

            form.append("size", "1920x1080");


            const response = await fetch("https://api.cometapi.com/v1/videos", {
              method: "POST",
              headers: { Authorization: `Bearer ${process.env.COMETAPI_KEY}` },
              body: form,
            });


            const result = await response.json();

            console.log(result);
components:
  schemas:
    CreateVideoResponse:
      type: object
      required:
        - id
        - object
        - model
        - status
        - progress
        - created_at
      properties:
        id:
          type: string
          description: Task id. Use it as the path parameter for GET /v1/videos/{id}.
        task_id:
          type: string
          description: Alias of id returned for compatibility. The value matches id.
        object:
          type: string
          description: Object type, always video.
        model:
          type: string
          description: Echo of the requested model id.
        status:
          type: string
          description: Initial task status. Newly created tasks are returned as queued.
          enum:
            - queued
            - in_progress
            - completed
            - failed
            - error
        progress:
          type: integer
          minimum: 0
          maximum: 100
          description: Completion percentage. 0 at creation.
        created_at:
          type: integer
          description: Task creation time as a Unix timestamp in seconds.
      additionalProperties: true
    ErrorResponse:
      description: >-
        Error body. The endpoint returns one of two shapes depending on where
        the validation fails.
      oneOf:
        - type: object
          properties:
            code:
              type:
                - string
                - 'null'
              description: Short error code such as invalid_request or InvalidParameter.
            message:
              type: string
              description: Human-readable error message.
          required:
            - message
          additionalProperties: true
        - type: object
          properties:
            error:
              type: object
              properties:
                code:
                  type:
                    - string
                    - 'null'
                message:
                  type: string
                type:
                  type: string
                  description: Error category, for example comet_api_error.
              required:
                - message
                - type
              additionalProperties: true
          required:
            - error
          additionalProperties: true
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      description: Bearer token authentication. Use your CometAPI key.

````