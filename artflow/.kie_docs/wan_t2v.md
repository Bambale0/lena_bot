# Wan 2.7 - Text to Video

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
      summary: Wan 2.7 - Text to Video
      deprecated: false
      description: >-
        ## Create Task


        Use this endpoint to create a new text-to-video generation task.


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
      operationId: wan-2-7-text-to-video
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
                    - wan/2-7-text-to-video
                  default: wan/2-7-text-to-video
                  description: |-
                    The model name used for generation. This field is required.

                    - This endpoint must use the `wan/2-7-text-to-video` model
                  examples:
                    - wan/2-7-text-to-video
                input:
                  type: object
                  description: Input parameters for the text-to-video task.
                  required:
                    - prompt
                  properties:
                    prompt:
                      type: string
                      minLength: 1
                      maxLength: 5000
                      description: >-
                        Positive prompt. Minimum length: 1 character. Maximum
                        length: 5000 characters.
                    negative_prompt:
                      type: string
                      maxLength: 500
                      description: 'Negative prompt. Maximum length: 500 characters.'
                    audio_url:
                      type: string
                      format: uri
                      description: Optional custom audio URL.
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
                    ratio:
                      type: string
                      enum:
                        - '16:9'
                        - '9:16'
                        - '1:1'
                        - '4:3'
                        - '3:4'
                      default: '16:9'
                      description: |-
                        Video aspect ratio.

                        - `16:9`: Landscape
                        - `9:16`: Portrait
                        - `1:1`: Square
                        - `4:3`: Landscape 4:3
                        - `3:4`: Portrait 3:4
                    duration:
                      type: integer
                      minimum: 2
                      maximum: 15
                      default: 5
                      description: |-
                        Video duration in seconds.

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
                    - audio_url
                    - resolution
                    - ratio
                    - duration
                    - prompt_extend
                    - watermark
                    - seed
                    - nsfw_checker
                callBackUrl:
                  type: string
                  format: uri
                  description: >-
                    Callback URL for task completion notifications. Optional
                    parameter. If provided, the system will send a POST request
                    to this URL when the task completes, whether it succeeds or
                    fails. If omitted, no callback notification will be sent.
              x-apidog-orders:
                - model
                - input
                - callBackUrl
            example:
              model: wan/2-7-text-to-video
              input:
                prompt: >-
                  A futuristic city street at night, neon reflections shimmering
                  on the wet ground. The camera slowly pushes forward as a
                  silver hover car glides in from the left. Giant holographic
                  billboards flicker in the distance, creating a cinematic
                  atmosphere.
                negative_prompt: blurry, low quality, flicker, distorted characters
                audio_url: https://your-domain.com/audio/custom-track.mp3
                resolution: 1080p
                ratio: '16:9'
                duration: 5
                prompt_extend: true
                watermark: false
                seed: 123456
              callBackUrl: https://your-domain.com/api/callback
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
      x-run-in-apidog: https://app.apidog.com/web/project/1184766/apis/api-32696915-run
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
