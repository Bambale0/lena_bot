# Kling 2.6 Image to Video

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
      summary: Kling 2.6 Image to Video
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

        In production environments, it is recommended to use the `callBackUrl`
        parameter to receive automatic notifications upon generation completion,
        rather than polling the status endpoint.

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
      operationId: kling-2-6-image-to-video
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
                    - kling-2.6/image-to-video
                  default: kling-2.6/image-to-video
                  description: >-
                    Name of the model used for the generation task. Required
                    field.


                    - This endpoint must use the `kling-2.6/image-to-video`
                    model
                  examples:
                    - kling-2.6/image-to-video
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

                    - Your callback endpoint needs to support receiving POST
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
                          In a bright rehearsal room, sunlight streams through
                          the windows, and a standing microphone is placed in
                          the center of the room. [Campus band female lead
                          singer] stands in front of the microphone with her
                          eyes closed, and other members stand around her.
                          [Campus band female lead singer, singing loudly] Lead
                          vocal: "I will do my best to heal you, with all my
                          heart and soul..." The background is a cappella
                          harmonies, and the camera slowly pans around the band
                          members.
                    image_urls:
                      description: >-
                        Image URLs for video generation. (Uploaded file URLs,
                        not file content; supported types: image/jpeg,
                        image/png, image/webp; maximum file size: 10.0MB)
                      type: array
                      items:
                        type: string
                        format: uri
                      maxItems: 1
                      examples:
                        - - >-
                            https://static.aiquickdraw.com/tools/example/1764851002741_i0lEiI8I.png
                    sound:
                      description: >-
                        This parameter specifies whether the generated video
                        contains sound (boolean: true/false)
                      type: boolean
                      examples:
                        - false
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
                    - image_urls
                    - sound
                    - duration
                  x-apidog-orders:
                    - prompt
                    - image_urls
                    - sound
                    - duration
                  x-apidog-ignore-properties: []
              x-apidog-orders:
                - model
                - callBackUrl
                - input
              x-apidog-ignore-properties: []
            example:
              model: kling-2.6/image-to-video
              callBackUrl: https://your-domain.com/api/callback
              input:
                prompt: >-
                  In a bright rehearsal room, sunlight streams through the
                  windows, and a standing microphone is placed in the center of
                  the room. [Campus band female lead singer] stands in front of
                  the microphone with her eyes closed, and other members stand
                  around her. [Campus band female lead singer, singing loudly]
                  Lead vocal: "I will do my best to heal you, with all my heart
                  and soul..." The background is a cappella harmonies, and the
                  camera slowly pans around the band members.
                image_urls:
                  - >-
                    https://static.aiquickdraw.com/tools/example/1764851002741_i0lEiI8I.png
                sound: false
                duration: '5'
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
                  taskId: task_kling-2.6_1765182405025
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
      x-run-in-apidog: https://app.apidog.com/web/project/1184766/apis/api-28506384-run
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
