# Grok Imagine Image to Video

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
      summary: Grok Imagine Image to Video
      deprecated: false
      description: >
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
      operationId: grok-imagine-image-to-video
      tags:
        - docs/en/Market/Video Models/Grok Imagine
      parameters: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                model:
                  type: string
                  enum:
                    - grok-imagine/image-to-video
                  default: grok-imagine/image-to-video
                  description: |-
                    The model name to use for generation. Required field.

                    - Must be `grok-imagine/image-to-video` for this endpoint
                  examples:
                    - grok-imagine/image-to-video
                callBackUrl:
                  type: string
                  format: uri
                  description: >-
                    The URL to receive video generation task completion updates.
                    Optional but recommended for production use.


                    - System will POST task status and results to this URL when
                    video generation completes

                    - Callback includes generated video URLs and task
                    information

                    - Your callback endpoint should accept POST requests with
                    JSON payload containing video results

                    - Alternatively, use the Get Task Details endpoint to poll
                    task status

                    - To ensure callback security, see [Webhook Verification
                    Guide](/common-api/webhook-verification) for signature
                    verification implementation
                  examples:
                    - https://your-domain.com/api/callback
                input:
                  type: object
                  description: Input parameters for the video generation task
                  properties:
                    image_urls:
                      type: array
                      items:
                        type: string
                        format: uri
                      description: >-
                        Provide an external image URL as a reference for video
                        generation. Up to 7 images are supported. Do not use it
                        simultaneously with task_id. In your prompt, reference
                        an uploaded image by typing @image(n) followed by a
                        space (for example: @image1 a sunset over the ocean).

                        - Supports JPEG, PNG, and WEBP formats

                        - Maximum file size for each image: 10MB

                        - The Spicy mode is not available when using external
                        images

                        - The array can contain a maximum of seven URLs
                      maxItems: 7
                      examples:
                        - - >-
                            https://file.aiquickdraw.com/custom-page/akr/section-images/1762247692373tw5di116.png
                    task_id:
                      type: string
                      description: >-
                        Task ID from a previously generated Grok image. Use with
                        index to select a specific image. Do not use with
                        image_urls.


                        - Use task ID from grok-imagine/text-to-image
                        generations

                        - Supports all modes including Spicy

                        - Maximum length: 100 characters
                      maxLength: 100
                      examples:
                        - task_grok_12345678
                    index:
                      type: integer
                      description: >-
                        When using task_id, specify which image to use (Grok
                        generates 6 images per task). Only works with task_id.


                        - 0-based index (0-5)

                        - Ignored if image_urls is provided

                        - Default: 0
                      minimum: 0
                      maximum: 5
                      default: 0
                      examples:
                        - 0
                    prompt:
                      type: string
                      description: >-
                        Text prompt describing the desired video motion.
                        Optional field.


                        - Should be detailed and specific about the desired
                        visual motion

                        - Describe movement, action sequences, camera work, and
                        timing

                        - Include details about subjects, environments, and
                        motion dynamics

                        - Maximum length: 5000 characters

                        - Supports English language prompts
                      examples:
                        - >-
                          POV hand comes into frame handing the girl a cup of
                          take away coffee, the girl steps out of the screen
                          looking tired, then takes it and she says happily:
                          "thanks! Back to work" she exits the frame and walks
                          right to a different part of the office.
                    mode:
                      type: string
                      description: >-
                        Specifies the generation mode affecting the style and
                        intensity of motion. Note: Spicy mode is not available
                        for external image inputs.


                        - **fun**: More creative and playful interpretation

                        - **normal**: Balanced approach with good motion quality

                        - **spicy**: More dynamic and intense motion effects
                        (not available for external images)


                        Default: normal
                      enum:
                        - fun
                        - normal
                        - spicy
                      default: normal
                      examples:
                        - normal
                    duration:
                      type: string
                      description: >-
                        The duration of the generated video (in seconds) (6-30).
                        (Minimum: 6, Maximum: 30, Step: 1)
                    resolution:
                      type: string
                      description: The resolution of the generated video.
                      enum:
                        - 480p
                        - 720p
                      x-apidog-enum:
                        - value: 480p
                          name: ''
                          description: ''
                        - value: 720p
                          name: ''
                          description: ''
                      default: 480p
                      examples:
                        - 480p
                    aspect_ratio:
                      type: string
                      description: >-
                        Image ratio selection only applies to multi-image
                        generation mode. In single-image mode, the video width
                        and height are referenced to the image width and height.
                      enum:
                        - '2:3'
                        - '3:2'
                        - '1:1'
                        - '16:9'
                        - '9:16'
                      x-apidog-enum:
                        - value: '2:3'
                          name: ''
                          description: ''
                        - value: '3:2'
                          name: ''
                          description: ''
                        - value: '1:1'
                          name: ''
                          description: ''
                        - value: '16:9'
                          name: ''
                          description: ''
                        - value: '9:16'
                          name: ''
                          description: ''
                      default: '16:9'
                    nsfw_checker:
                      type: boolean
                      description: >-
                        Defaults to false. You can set it to false based on your
                        needs. If set to false, our content filtering will be
                        disabled, and all results will be returned directly by
                        the model itself.
                      default: false
                  x-apidog-orders:
                    - image_urls
                    - task_id
                    - index
                    - prompt
                    - mode
                    - duration
                    - resolution
                    - aspect_ratio
                    - nsfw_checker
                  x-apidog-ignore-properties: []
              required:
                - model
                - input
              x-apidog-orders:
                - model
                - callBackUrl
                - input
              examples:
                - model: grok-imagine/image-to-video
                  callBackUrl: https://your-domain.com/api/callback
                  input:
                    image_urls:
                      - >-
                        https://file.aiquickdraw.com/custom-page/akr/section-images/1762247692373tw5di116.png
                    prompt: >-
                      POV hand comes into frame handing the girl a cup of take
                      away coffee, the girl steps out of the screen looking
                      tired, then takes it and she says happily: "thanks! Back
                      to work" she exits the frame and walks right to a
                      different part of the office.
                    mode: normal
              x-apidog-ignore-properties: []
            example:
              model: grok-imagine/image-to-video
              callBackUrl: https://your-domain.com/api/callback
              input:
                task_id: task_grok_12345678
                image_urls:
                  - >-
                    https://file.aiquickdraw.com/custom-page/akr/section-images/1762247692373tw5di116.png
                prompt: >-
                  POV hand comes into frame handing the girl a cup of take away
                  coffee, the girl steps out of the screen looking tired, then
                  takes it and she says happily: "thanks! Back to work" she
                  exits the frame and walks right to a different part of the
                  office.
                mode: normal
                duration: '6'
                resolution: 480p
                aspect_ratio: '16:9'
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
                  taskId: 281e5b0*********************f39b9
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
      x-apidog-folder: docs/en/Market/Video Models/Grok Imagine
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/1184766/apis/api-28506396-run
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
