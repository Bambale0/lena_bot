# Kling 2.6 Text to Video

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
      summary: Kling 2.6 Text to Video
      deprecated: false
      description: >-
        ## Query Task Status


        After submitting a task, you can check the task progress and retrieve
        generation results via the unified query endpoint:


        <Card title="Get Task Details" icon="lucide-search"
        href="/market/common/get-task-detail">
          Learn how to query task status and obtain generation results
        </Card>


        ::: tip[]

        For production use, we recommend using the `callBackUrl` parameter to
        receive automatic notifications when generation completes, rather than
        polling the status endpoint.

        :::


        ## Related Resources


        <CardGroup cols={2}>
          <Card title="Market Overview" icon="lucide-store" href="/market/quickstart">
            Browse all available models
          </Card>
          <Card title="Common API" icon="lucide-cog" href="/common-api/get-account-credits">
            Check account credits and usage status
          </Card>
        </CardGroup>
      operationId: kling-2-6-text-to-video
      tags:
        - docs/en/Market/Video Models/Kling
      parameters: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              required:
                - model
              properties:
                model:
                  type: string
                  enum:
                    - kling-2.6/text-to-video
                  default: kling-2.6/text-to-video
                  description: >-
                    Name of the model used for the generation task. Required
                    field.


                    - This endpoint must use the `kling-2.6/text-to-video` model
                  examples:
                    - kling-2.6/text-to-video
                callBackUrl:
                  type: string
                  format: uri
                  description: >-
                    Callback URL to receive notifications when the generation
                    task is completed. Optional configuration, recommended for
                    production environments.


                    - After the task is completed, the system will POST the task
                    status and results to this URL

                    - The callback content includes the generated resource URL
                    and task-related information

                    - Your callback endpoint must support receiving POST
                    requests with JSON payloads

                    - You can also choose to call the task details endpoint to
                    actively poll the task status

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
                      description: >-
                        Text prompt for video generation (maximum length: 1000
                        characters)
                      type: string
                      maxLength: 1000
                      examples:
                        - >-
                          Scene: A fashion live-streaming sales setting, with
                          clothes hanging on racks and the host's figure
                          reflected in a full-length mirror. Lines: [African
                          female host] turns around to showcase the hoodie's
                          cut. [African female host, in a cheerful tone] says:
                          "360-degree flawless tailoring, slimming and
                          versatile." She then [African female host] leans
                          closer to the camera. [African female host, in a
                          lively tone] says: "Double-sided fleece fabric, $30
                          off immediately when you order now."
                    sound:
                      description: >-
                        This parameter specifies whether the generated video
                        contains sound (boolean: true/false)
                      type: boolean
                      examples:
                        - false
                    aspect_ratio:
                      description: This parameter defines the video aspect ratio
                      type: string
                      enum:
                        - '1:1'
                        - '16:9'
                        - '9:16'
                      default: '1:1'
                      examples:
                        - '1:1'
                    duration:
                      description: 'Video duration (unit: seconds)'
                      type: string
                      enum:
                        - '5'
                        - '10'
                      default: '5'
                      examples:
                        - '5'
                  required:
                    - prompt
                    - sound
                    - aspect_ratio
                    - duration
                  x-apidog-orders:
                    - prompt
                    - sound
                    - aspect_ratio
                    - duration
                  x-apidog-ignore-properties: []
              x-apidog-orders:
                - model
                - callBackUrl
                - input
              x-apidog-ignore-properties: []
            example:
              model: kling-2.6/text-to-video
              callBackUrl: https://your-domain.com/api/callback
              input:
                prompt: >-
                  Scene: A fashion live-streaming sales setting, with clothes
                  hanging on racks and the host's figure reflected in a
                  full-length mirror. Lines: [African female host] turns around
                  to showcase the hoodie's cut. [African female host, in a
                  cheerful tone] says: "360-degree flawless tailoring, slimming
                  and versatile." She then [African female host] leans closer to
                  the camera. [African female host, in a lively tone] says:
                  "Double-sided fleece fabric, $30 off immediately when you
                  order now."
                sound: false
                aspect_ratio: '1:1'
                duration: '5'
      responses:
        '200':
          description: Request Successful
          content:
            application/json:
              schema:
                allOf:
                  - $ref: '#/components/schemas/ApiResponse'
              example:
                code: 200
                msg: success
                data:
                  taskId: task_kling-2.6_1765182425861
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
      x-apidog-folder: docs/en/Market/Video Models/Kling
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/1184766/apis/api-28506383-run
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
