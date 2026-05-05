# HappyHorse - text-to-video

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
      summary: HappyHorse - text-to-video
      deprecated: false
      description: >-
        ## Query Task Status


        After submitting a task, use the unified query endpoint to check
        progress and retrieve results:


        <Card title="Get Task Details" icon="lucide-search"
        href="/market/common/get-task-detail">
          Learn how to query task status and retrieve generation results
        </Card>


        ::: tip[]

        For production use, we recommend using the `callBackUrl` parameter to
        receive automatic notifications when generation completes, rather than
        polling the status endpoint.

        :::


        ## Related Resources


        <CardGroup cols={2}>
          <Card title="Market Overview" icon="lucide-store" href="/market/quickstart">
            Explore all available models
          </Card>
          <Card title="Common API" icon="lucide-cog" href="/common-api/get-account-credits">
            Check credits and account usage
          </Card>
        </CardGroup>
      operationId: happyhorse-text-to-video
      tags:
        - docs/en/Market/Video Models/HappyHorse
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
                  description: |-
                    The model name to use for generation. Required field.

                    - Must be `happyhorse/text-to-video` for this endpoint
                  enum:
                    - happyhorse/text-to-video
                  default: happyhorse/text-to-video
                  x-apidog-enum:
                    - value: happyhorse/text-to-video
                      name: ''
                      description: ''
                  examples:
                    - happyhorse/text-to-video
                callBackUrl:
                  type: string
                  format: uri
                  description: >-
                    The URL to receive generation task completion updates.
                    Optional but recommended for production use.


                    - System will POST task status and results to this URL when
                    generation completes

                    - Callback includes generated content URLs and task
                    information

                    - Your callback endpoint should accept POST requests with
                    JSON payload containing results

                    - Alternatively, use the Get Task Details endpoint to poll
                    task status

                    - To ensure callback security, see [Webhook Verification
                    Guide](/common-api/webhook-verification) for signature
                    verification implementation
                  examples:
                    - https://your-domain.com/api/callback
                input:
                  type: object
                  description: Input parameters for the generation task
                  properties:
                    prompt:
                      type: string
                      description: >-
                        Text prompt describing the video to generate (any
                        language). Max 5,000 non‑Chinese characters or 2,500
                        Chinese characters; extra content is truncated.
                      maxLength: 5000
                      examples:
                        - >-
                          A miniature city built from cardboard and bottle caps
                          comes to life at night. A cardboard train slowly
                          passes through, with small lights dotting the scene
                          and illuminating the way ahead.
                    resolution:
                      type: string
                      description: >-
                        Output video resolution. Valid values: 720P, 1080P
                        (default).
                      enum:
                        - 720p
                        - 1080p
                      default: 1080p
                      x-apidog-enum:
                        - value: 720p
                          name: ''
                          description: ''
                        - value: 1080p
                          name: ''
                          description: ''
                      examples:
                        - 1080p
                    aspect_ratio:
                      type: string
                      description: >-
                        Output aspect ratio. Valid values: 16:9 (default), 9:16,
                        1:1, 4:3, 3:4.
                      enum:
                        - '16:9'
                        - '9:16'
                        - '1:1'
                        - '4:3'
                        - '3:4'
                      default: '16:9'
                      x-apidog-enum:
                        - value: '16:9'
                          name: ''
                          description: ''
                        - value: '9:16'
                          name: ''
                          description: ''
                        - value: '1:1'
                          name: ''
                          description: ''
                        - value: '4:3'
                          name: ''
                          description: ''
                        - value: '3:4'
                          name: ''
                          description: ''
                      examples:
                        - '16:9'
                    duration:
                      type: integer
                      description: >-
                        Output duration in seconds (integer). Must be between 3
                        and 15. Defaults to 5.
                      default: 5
                      examples:
                        - 5
                      minimum: 3
                      maximum: 15
                    seed:
                      type: integer
                      description: Random seed for reproducibility (if supported).
                      default: 0
                      minimum: 0
                      maximum: 2147483647
                  x-apidog-orders:
                    - prompt
                    - resolution
                    - aspect_ratio
                    - duration
                    - seed
                  required:
                    - prompt
                  x-apidog-ignore-properties: []
              x-apidog-orders:
                - model
                - callBackUrl
                - input
              x-apidog-ignore-properties: []
            example:
              model: happyhorse/text-to-video
              callBackUrl: https://your-domain.com/api/callback
              input:
                prompt: >-
                  A miniature city built from cardboard and bottle caps comes to
                  life at night. A cardboard train slowly passes through, with
                  small lights dotting the scene and illuminating the way ahead.
                resolution: 1080p
                aspect_ratio: '16:9'
                duration: 5
                seed: 1622429582
      responses:
        '200':
          description: Request successful
          content:
            application/json:
              schema:
                allOf:
                  - $ref: '#/components/schemas/ApiResponse'
              example:
                code: 200
                msg: success
                data:
                  taskId: task_bytedance_1765186743319
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
      x-apidog-folder: docs/en/Market/Video Models/HappyHorse
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/1184766/apis/api-34245310-run
components:
  schemas:
    ApiResponse:
      type: object
      properties:
        code:
          type: integer
          description: >-
            Response status code


            - **200**: Success - Request has been processed successfully

            - **401**: Unauthorized - Authentication credentials are missing or
            invalid

            - **402**: Insufficient Credits - Account does not have enough
            credits to perform the operation

            - **404**: Not Found - The requested resource or endpoint does not
            exist

            - **422**: Validation Error - The request parameters failed
            validation checks

            - **429**: Rate Limited - Request limit has been exceeded for this
            resource

            - **433**: Request Limit - Sub-key Usage Exceeds Limit

            - **455**: Service Unavailable - System is currently undergoing
            maintenance

            - **500**: Server Error - An unexpected error occurred while
            processing the request

            - **501**: Generation Failed - Content generation task failed

            - **505**: Feature Disabled - The requested feature is currently
            disabled
          enum:
            - 200
            - 401
            - 402
            - 404
            - 422
            - 429
            - 433
            - 455
            - 500
            - 501
            - 505
          x-apidog-enum:
            - value: 200
              name: ''
              description: ''
            - value: 401
              name: ''
              description: ''
            - value: 402
              name: ''
              description: ''
            - value: 404
              name: ''
              description: ''
            - value: 422
              name: ''
              description: ''
            - value: 429
              name: ''
              description: ''
            - value: 433
              name: ''
              description: ''
            - value: 455
              name: ''
              description: ''
            - value: 500
              name: ''
              description: ''
            - value: 501
              name: ''
              description: ''
            - value: 505
              name: ''
              description: ''
        msg:
          type: string
          description: Response message, error description when failed
          examples:
            - success
        data:
          type: object
          properties:
            taskId:
              type: string
              description: >-
                Task ID, can be used with Get Task Details endpoint to query
                task status
          x-apidog-orders:
            - taskId
          required:
            - taskId
          x-apidog-ignore-properties: []
      x-apidog-orders:
        - code
        - msg
        - data
      title: response not with recordId
      required:
        - data
      x-apidog-ignore-properties: []
      x-apidog-folder: ''
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
