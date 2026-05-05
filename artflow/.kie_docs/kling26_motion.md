# Kling 2.6 motion-control

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
      summary: Kling 2.6 motion-control
      deprecated: false
      description: >
        ## File Upload Requirements


        Before using the Motion Control API, you need to upload your image and
        video files:


        <Steps>

        <Step title="Upload Reference Image">
          Use the File Upload API to upload your reference image showing the subject.

          <Card title="File Upload API" icon="lucide-upload" href="/file-upload-api/quickstart">
            Learn how to upload images and get file URLs
          </Card>

          **Requirements:**
          - **File Type**: JPEG, PNG, or JPG format
          - **Max File Size**: 10MB per file
          - **Content**: Clear image showing the subject's head, shoulders, and torso
        </Step>


        <Step title="Upload Motion Video">
          Upload a video that defines the motion pattern you want to apply.

          **Requirements:**
          - **File Type**: MP4, QuickTime, or Matroska format
          - **Duration**: Between 3-30 seconds per video
          - **Max File Size**: 100MB per file
          - **Content**: Video clearly showing the subject's head, shoulders, and torso
        </Step>


        <Step title="Get File URLs">
          After upload, you'll receive file URLs that you can use in the `input_urls` and `video_urls` parameters.
        </Step>

        </Steps>


        ::: warning[]

        - Supported image formats: JPEG, PNG, JPG (Max: 10MB)

        - Supported video formats: MP4, QuickTime, Matroska (Max: 100MB, 3-30
        seconds)

        - Videos must clearly show the subject's head, shoulders, and torso

        - Maximum one image and one video per request

        :::


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
      operationId: kling-2-6-motion-control
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
                    - kling-2.6/motion-control
                  default: kling-2.6/motion-control
                  description: |-
                    The model name to use for generation. Required field.

                    - Must be `kling-2.6/motion-control` for this endpoint
                  examples:
                    - kling-2.6/motion-control
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
                      description: >-
                        A text description of the desired output. Maximum length
                        is 2500 characters. (Max length: 2500 characters)
                      type: string
                      maxLength: 2500
                      examples:
                        - The cartoon character is dancing.
                    input_urls:
                      description: >-
                        An array containing a single image URL. The photo must
                        clearly show the subject's head, shoulders, and torso.
                        (File URL after upload, not file content; Accepted
                        types: image/jpeg, image/png, image/jpg; Max size:
                        10.0MB,size needs to be greater than 300px, aspect ratio
                        2:5 to 5:2.)
                      type: array
                      items:
                        type: string
                        format: uri
                      maxItems: 1
                      examples:
                        - - >-
                            https://static.aiquickdraw.com/tools/example/1767694885407_pObJoMcy.png
                    video_urls:
                      description: >-
                        An array containing a single video URL. The duration
                        must be between 3 to 30 seconds, and the video must
                        clearly show the subject's head, shoulders, and torso.
                        (File URL after upload, not file content; Accepted
                        types: video/mp4, video/quicktime, video/x-matroska; Max
                        size: 100.0MB)
                      type: array
                      items:
                        type: string
                        format: uri
                      maxItems: 1
                      examples:
                        - - >-
                            https://static.aiquickdraw.com/tools/example/1767525918769_QyvTNib2.mp4
                    character_orientation:
                      description: >-
                        Generate the orientation of the characters in the video.
                        'image': same orientation as the person in the picture
                        (max 10s video). 'video': consistent with the
                        orientation of the characters in the video (max 30s
                        video).
                      type: string
                      enum:
                        - image
                        - video
                      default: video
                      examples:
                        - video
                    mode:
                      description: >-
                        Output resolution mode. Use 'std' for 720p or 'pro' for
                        1080p.
                      type: string
                      enum:
                        - 720p
                        - 1080p
                      default: 720p
                      examples:
                        - 720p
                  required:
                    - input_urls
                    - video_urls
                    - character_orientation
                    - mode
                  x-apidog-orders:
                    - prompt
                    - input_urls
                    - video_urls
                    - character_orientation
                    - mode
                  x-apidog-ignore-properties: []
              x-apidog-orders:
                - model
                - callBackUrl
                - input
              x-apidog-ignore-properties: []
            example:
              model: kling-2.6/motion-control
              callBackUrl: https://your-domain.com/api/callback
              input:
                prompt: The cartoon character is dancing.
                input_urls:
                  - >-
                    https://static.aiquickdraw.com/tools/example/1767694885407_pObJoMcy.png
                video_urls:
                  - >-
                    https://static.aiquickdraw.com/tools/example/1767525918769_QyvTNib2.mp4
                mode: 720p
                character_orientation: image
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
                  taskId: task_kling-2.6_1767693973938
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
      x-run-in-apidog: https://app.apidog.com/web/project/1184766/apis/api-28506391-run
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
