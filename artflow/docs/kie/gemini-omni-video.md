# Gemini Omni Video

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/v1/jobs/createTask:
    post:
      summary: Gemini Omni Video
      deprecated: false
      description: >+
        ## Create Task


        Use this endpoint to create a new multimodal video generation task.


        <Card title="Get Task Details" icon="lucide-search"
        href="/market/common/get-task-detail">
          After submission, use the unified query endpoint to check task progress and retrieve results
        </Card>


        ::: tip[]

        For production use, we recommend providing the `callBackUrl` parameter
        so your service can receive completion notifications instead of polling
        for task status.

        :::


        ## Related Resources


        <CardGroup cols={2}>
          <Card title="Model Marketplace" icon="lucide-store" href="/market/quickstart">
            Explore all available models and capabilities
          </Card>
          <Card title="Common API" icon="lucide-cog" href="/common-api/get-account-credits">
            Check account credits and usage
          </Card>
        </CardGroup>


        **Total Quota Overview:**

        The system utilizes a quota-based system for content uploads. The total
        available capacity is **7 units**. Different parameters consume
        different amounts of this quota. Please ensure the sum of all consumed
        units does not exceed 7.


        **Quota Consumption Rules:**

        1.  **Images (`image_urls`)**: Each image consumes **1 unit**.

        2.  **Videos (`video_list`)**: Each video consumes **2 units**.
            *   *Note: Maximum of 1 video per request.*
        3.  **Character IDs (`character_ids`)**: Each ID consumes **1 unit**.
            *   *Note: Maximum of 3 character IDs per request.*

        **Constraint Formula:**

        `(Number of Images) + (Number of Videos × 2) + (Number of Character IDs)
        ≤ 7`


        **Example Scenarios:**

        *   If 1 video (2 units) and 3 Character IDs (3 units) are uploaded, you
        can upload a maximum of 2 additional images.

        *   If no video or Character IDs are provided, you can upload up to 7
        images.


      operationId: gemini-omni-video
      tags:
        - docs/en/Market/Video Models/Gemini Omni
      parameters: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              required:
                - model
                - input
              properties:
                model:
                  type: string
                  enum:
                    - gemini-omni-video
                  default: gemini-omni-video
                  description: >-
                    The model name used for generation. This field is required.
                    This endpoint must use the `gemini-omni-video` model.
                  examples:
                    - gemini-omni-video
                callBackUrl:
                  type: string
                  format: uri
                  description: >-
                    Callback URL for task completion notifications. Optional
                    parameter. If provided, the system will send a POST request
                    to this URL when the task completes, whether it succeeds or
                    fails. If omitted, no callback notification will be sent.
                  examples:
                    - https://your-domain.com/api/callback
                input:
                  type: object
                  description: Input parameters for the multimodal video generation task.
                  properties:
                    prompt:
                      type: string
                      description: >-
                        Video prompt used to describe the target content, style,
                        camera language, or character actions in the generated
                        video.
                      examples:
                        - >-
                          Create a futuristic night city short film with a slow
                          push-in shot as the character walks out from a
                          neon-lit street.
                    image_urls:
                      type: array
                      items:
                        type: string
                        format: uri
                      description: >-
                        Array of image URLs. You can provide one or more
                        reference images for characters, scenes, styles, or
                        storyboard guidance.


                        Image limits:

                        - Each file must be no larger than `20MB`

                        - Use publicly accessible image URLs

                        - Max 7 images
                      examples:
                        - - https://example.com/assets/scene-1.png
                          - https://example.com/assets/scene-2.png
                    audio_ids:
                      type: array
                      items:
                        type: string
                      description: >-
                        Array of audio IDs generated by the `gemini-omni-audio`
                        endpoint. Useful for narration, dialogue, music, or
                        audio guidance in the generated video. Max 1 item.
                      examples:
                        - - audio_01hx8p0demo
                    video_list:
                      type: array
                      items:
                        type: object
                        required:
                          - url
                          - start
                          - ends
                        properties:
                          url:
                            type: string
                            format: uri
                            description: >-
                              Video URL. Each source video file must be no
                              larger than `100MB` and no longer than `30s`.
                          start:
                            type: number
                            minimum: 0
                            description: Start time in seconds.
                          ends:
                            type: number
                            minimum: 0
                            description: >-
                              End time in seconds. It should be greater than
                              `start`.The difference between the end time and
                              the start time must not exceed 10s
                        x-apidog-orders:
                          - url
                          - start
                          - ends
                      description: >-
                        Array of video clips. Each item defines a source video
                        and the trim range to use during generation.


                        Video limits:

                        - Each file must be no larger than `100MB`

                        - Video duration must not exceed `30s`

                        - `ends` should be greater than `start`

                        - The difference between the end time and the start time
                        must not exceed `10s`.

                        - Max 1 items. Equal 2 images
                      examples:
                        - - url: https://example.com/assets/source-video.mp4
                            start: 0
                            ends: 10
                    character_ids:
                      type: array
                      items:
                        type: string
                      description: >-
                        An array of character IDs generated by the
                        `gemini-omni-character` API. Used to provide character
                        appearance, identity, or person references for the
                        video. Each character_id uses 1 image slot. The base
                        limit is 7 image slots; if video_list is also provided,
                        video_list uses 2 image slots, so character_ids can
                        contain up to 3 IDs.
                      examples:
                        - - character_01hx8p0demo
                    duration:
                      type: string
                      enum:
                        - '4'
                        - '6'
                        - '8'
                        - '10'
                      description: >-
                        The duration of the generated video in seconds.
                        Available values are 4, 6, 8, and 10. When video input
                        is provided, the output duration is determined by the
                        model automatically. This duration parameter will not
                        take effect.Note: when video input is provided, the
                        output duration is determined by the model
                        automatically. This duration parameter will not take
                        effect.
                      examples:
                        - '8'
                    aspect_ratio:
                      type: string
                      enum:
                        - '16:9'
                        - '9:16'
                      description: >-
                        The aspect ratio of the generated video. `16:9` is
                        landscape, and `9:16` is portrait.
                      examples:
                        - '16:9'
                    seed:
                      type: integer
                      description: >-
                        Random seed. Range: [0, 2147483647]. If not specified,
                        the system generates a seed automatically. Fixing the
                        seed can improve reproducibility, but results may still
                        vary due to the model’s stochasticity.
                    resolution:
                      type: string
                      enum:
                        - 720p
                        - 1080p
                        - 4k
                      description: >-
                        The resolution of the generated video. Available values
                        are 720p, 1080p, and 4k.
                      default: 720p
                      examples:
                        - 720p
                  x-apidog-orders:
                    - prompt
                    - image_urls
                    - audio_ids
                    - video_list
                    - character_ids
                    - duration
                    - aspect_ratio
                    - resolution
                    - seed
                  required:
                    - prompt
                    - duration
              x-apidog-orders:
                - model
                - callBackUrl
                - input
            example:
              model: gemini-omni-video
              callBackUrl: https://your-domain.com/api/callback
              input:
                prompt: >-
                  Create a futuristic night city short film with a slow push-in
                  shot as the character walks out from a neon-lit street.
                image_urls:
                  - https://example.com/assets/scene-1.png
                  - https://example.com/assets/scene-2.png
                audio_ids:
                  - audio_01hx8p0demo
                video_list:
                  - url: https://example.com/assets/source-video.mp4
                    start: 0
                    ends: 10
                duration: '4'
      responses:
        '200':
          description: Request successful
          content:
            application/json:
              schema:
                allOf:
                  - type: object
                    properties: {}
                  - type: object
                    properties:
                      data:
                        type: object
                        properties:
                          taskId:
                            type: string
                            description: >-
                              Task ID, which can be used to query task status
                              through the task detail endpoint.
                            examples:
                              - task_gemini_1765180586443
                        x-apidog-orders:
                          - taskId
                    x-apidog-orders:
                      - data
              example:
                code: 200
                msg: success
                data:
                  taskId: task_gemini_1765180586443
          headers: {}
          x-apidog-name: ''
      security:
        - BearerAuth: []
          x-apidog:
            schemeGroups:
              - id: kn8M4YUlc5i0A0179ezwx
                schemeIds:
                  - BearerAuth
            required: true
            use:
              id: kn8M4YUlc5i0A0179ezwx
            scopes:
              kn8M4YUlc5i0A0179ezwx:
                BearerAuth: []
      x-apidog-folder: docs/en/Market/Video Models/Gemini Omni
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/1184766/apis/api-36212673-run
components:
  schemas: {}
  securitySchemes:
    BearerAuth:
      type: bearer
      scheme: bearer
      bearerFormat: API Key
      description: |-
        所有 API 都需要通过 Bearer Token 进行身份验证。

        获取 API Key：
        1. 访问 [API Key 管理页面](https://kie.ai/api-key) 获取您的 API Key

        使用方法：
        在请求头中添加：
        Authorization: Bearer YOUR_API_KEY

        注意事项：
        - 请妥善保管您的 API Key，切勿泄露给他人
        - 若怀疑 API Key 泄露，请立即在管理页面重置
    BearerAuth1:
      type: bearer
      scheme: bearer
      bearerFormat: API Key
      description: |-
        所有 API 都需要通过 Bearer Token 进行身份验证。

        获取 API Key：
        1. 访问 [API Key 管理页面](https://kie.ai/api-key) 获取您的 API Key

        使用方法：
        在请求头中添加：
        Authorization: Bearer YOUR_API_KEY

        注意事项：
        - 请妥善保管您的 API Key，切勿泄露给他人
        - 若怀疑 API Key 泄露，请立即在管理页面重置
servers:
  - url: https://api.kie.ai
    description: 正式环境
security:
  - BearerAuth: []
    x-apidog:
      schemeGroups:
        - id: kn8M4YUlc5i0A0179ezwx
          schemeIds:
            - BearerAuth
      required: true
      use:
        id: kn8M4YUlc5i0A0179ezwx
      scopes:
        kn8M4YUlc5i0A0179ezwx:
          BearerAuth: []

```
