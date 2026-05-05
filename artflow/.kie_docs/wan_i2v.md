# Wan 2.7 - Image to Video

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
      summary: Wan 2.7 - Image to Video
      deprecated: false
      description: >-
        ## Create Task


        Use this endpoint to create a new image-to-video generation task.


        This model supports the following three generation modes:


        - First-frame-to-video: provide `first_frame_url` only

        - First-and-last-frame-to-video: provide both `first_frame_url` and
        `last_frame_url`

        - Video continuation: provide `first_clip_url`


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
      operationId: wan-2-7-image-to-video
      tags:
        - docs/en/Market/Video Models/Wan
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
                    - wan/2-7-image-to-video
                  default: wan/2-7-image-to-video
                  description: >-
                    The model name used for generation. This field is required.
                    This endpoint must use the `wan/2-7-image-to-video` model.
                  examples:
                    - wan/2-7-image-to-video
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
                  description: Input parameters for the image-to-video task.
                  properties:
                    prompt:
                      type: string
                      maxLength: 5000
                      description: 'Positive prompt. Maximum length: 5000 characters.'
                    negative_prompt:
                      type: string
                      maxLength: 500
                      description: 'Negative prompt. Maximum length: 500 characters.'
                    first_frame_url:
                      type: string
                      format: uri
                      description: First frame image URL.
                    last_frame_url:
                      type: string
                      format: uri
                      description: Last frame image URL.
                    first_clip_url:
                      type: string
                      format: uri
                      description: First clip video URL, used for video continuation.
                    driving_audio_url:
                      type: string
                      format: uri
                      description: Driving audio URL.
                    resolution:
                      type: string
                      enum:
                        - 720p
                        - 1080p
                      default: 1080p
                      description: |-
                        Video resolution. 

                        - `720p`: 720p
                        - `1080p`: 1080p
                    duration:
                      type: integer
                      minimum: 2
                      maximum: 15
                      default: 5
                      description: |-
                        Total output video duration in seconds.

                        - Minimum: `2`
                        - Maximum: `15`
                        - Default: `5`
                    prompt_extend:
                      type: boolean
                      default: true
                      description: >-
                        Whether to enable intelligent prompt rewriting. Default
                        value: `true`.
                    watermark:
                      type: boolean
                      default: false
                      description: >-
                        Whether to add an AI-generated watermark. Default value:
                        `false`.
                    seed:
                      type: integer
                      minimum: 0
                      maximum: 2147483647
                      description: |-
                        Random seed.

                        - Minimum: `0`
                        - Maximum: `2147483647`
                    nsfw_checker:
                      type: boolean
                      description: >-
                        Defaults to false. You can set it to false based on your
                        needs. If set to false, our content filtering will be
                        disabled, and all results will be returned directly by
                        the model itself.
                  x-apidog-orders:
                    - prompt
                    - negative_prompt
                    - first_frame_url
                    - last_frame_url
                    - first_clip_url
                    - driving_audio_url
                    - resolution
                    - duration
                    - prompt_extend
                    - watermark
                    - seed
                    - nsfw_checker
                  required:
                    - prompt
              x-apidog-orders:
                - model
                - callBackUrl
                - input
            examples:
              '1':
                value:
                  model: wan/2-7-image-to-video
                  callBackUrl: https://your-domain.com/api/callback
                  input:
                    prompt: >-
                      A white cat stands on a windowsill in warm afternoon
                      light. The camera slowly pushes in as the cat blinks
                      softly and turns to look outside.
                    negative_prompt: blurry, flicker, low quality, distorted
                    first_frame_url: https://your-domain.com/assets/first-frame.png
                    last_frame_url: https://your-domain.com/assets/last-frame.png
                    resolution: 1080p
                    duration: 5
                    prompt_extend: true
                    watermark: false
                    seed: 123456
                summary: First and last frame to video
              '2':
                value:
                  model: wan/2-7-image-to-video
                  callBackUrl: https://your-domain.com/api/callback
                  input:
                    prompt: >-
                      A white cat stands on a windowsill in warm afternoon
                      light. The camera slowly pushes in as the cat blinks
                      softly and turns to look outside.
                    negative_prompt: blurry, flicker, low quality, distorted
                    first_frame_url: https://your-domain.com/assets/first-frame.png
                    driving_audio_url: https://your-domain.com/assets/driving-audio.mp3
                    resolution: 1080p
                    duration: 5
                    prompt_extend: true
                    watermark: false
                    seed: 123456
                summary: First frame to video
              '3':
                value:
                  model: wan/2-7-image-to-video
                  callBackUrl: https://your-domain.com/api/callback
                  input:
                    prompt: >-
                      A white cat stands on a windowsill in warm afternoon
                      light. The camera slowly pushes in as the cat blinks
                      softly and turns to look outside.
                    negative_prompt: blurry, flicker, low quality, distorted
                    first_clip_url: https://your-domain.com/assets/first-clip.mp4
                    resolution: 1080p
                    duration: 5
                    prompt_extend: true
                    watermark: false
                    seed: 123456
                summary: Video continuation
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
                              - task_wan_1765180586443
                        x-apidog-orders:
                          - taskId
                    x-apidog-orders:
                      - data
              example:
                code: 200
                msg: success
                data:
                  taskId: task_wan_1765180586443
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
      x-apidog-folder: docs/en/Market/Video Models/Wan
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/1184766/apis/api-32701090-run
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
