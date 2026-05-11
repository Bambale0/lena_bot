# Qwen - Image Edit

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
      summary: Qwen - Image Edit
      deprecated: false
      description: >-
        Image generation by qwen/image-edit


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
      operationId: qwen-image-edit
      tags:
        - docs/en/Market/Image    Models/Qwen
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
                    - qwen/image-edit
                  default: qwen/image-edit
                  description: |-
                    The model name to use for generation. Required field.

                    - Must be `qwen/image-edit` for this endpoint
                  examples:
                    - qwen/image-edit
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
                        The prompt to generate the image with (Max length: 2000
                        characters)
                      type: string
                      maxLength: 2000
                      examples:
                        - ''
                    image_url:
                      description: >-
                        The URL of the image to edit. (File URL after upload,
                        not file content; Accepted types: image/jpeg, image/png,
                        image/webp; Max size: 10.0MB)
                      type: string
                      examples:
                        - >-
                          https://file.aiquickdraw.com/custom-page/akr/section-images/1755603225969i6j87xnw.jpg
                    acceleration:
                      description: >-
                        Acceleration level for image generation. Options:
                        'none', 'regular'. Higher acceleration increases speed.
                        'regular' balances speed and quality. Default value:
                        "none"
                      type: string
                      enum:
                        - none
                        - regular
                        - high
                      default: none
                      examples:
                        - none
                    image_size:
                      description: >-
                        The size of the generated image. Default value:
                        landscape_4_3
                      type: string
                      enum:
                        - square
                        - square_hd
                        - portrait_4_3
                        - portrait_16_9
                        - landscape_4_3
                        - landscape_16_9
                      default: landscape_4_3
                      examples:
                        - landscape_4_3
                    num_inference_steps:
                      description: >-
                        The number of inference steps to perform. Default value:
                        30 (Min: 2, Max: 49, Step: 1) (step: 1)
                      type: number
                      minimum: 2
                      maximum: 49
                      default: 25
                      examples:
                        - 25
                    seed:
                      description: >-
                        The same seed and the same prompt given to the same
                        version of the model will output the same image every
                        time.
                      type: integer
                    guidance_scale:
                      description: >-
                        The CFG (Classifier Free Guidance) scale is a measure of
                        how close you want the model to stick to your prompt
                        when looking for a related image to show you. Default
                        value: 4 (Min: 0, Max: 20, Step: 0.1) (step: 0.1)
                      type: number
                      minimum: 0
                      maximum: 20
                      default: 4
                      examples:
                        - 4
                    sync_mode:
                      description: >-
                        If set to true, the function will wait for the image to
                        be generated and uploaded before returning the response.
                        This will increase the latency of the function but it
                        allows you to get the image directly in the response
                        without going through the CDN. (Boolean value
                        (true/false))
                      type: boolean
                      examples:
                        - false
                    num_images:
                      description: num_images
                      type: string
                      enum:
                        - '1'
                        - '2'
                        - '3'
                        - '4'
                    enable_safety_checker:
                      description: >-
                        If set to true, the safety checker will be enabled.
                        Default value: true (Boolean value (true/false))
                      type: boolean
                      examples:
                        - true
                    output_format:
                      description: 'The format of the generated image. Default value: "png"'
                      type: string
                      enum:
                        - jpeg
                        - png
                      default: png
                      examples:
                        - png
                    negative_prompt:
                      description: >-
                        The negative prompt for the generation Default value: "
                        " (Max length: 500 characters)
                      type: string
                      maxLength: 500
                      examples:
                        - blurry, ugly
                    nsfw_checker:
                      type: boolean
                      default: false
                      description: >-
                        Defaults to false. You can set it to false based on your
                        needs. If set to false, our content filtering will be
                        disabled, and all results will be returned directly by
                        the model itself.
                  required:
                    - prompt
                    - image_url
                  x-apidog-orders:
                    - prompt
                    - image_url
                    - acceleration
                    - image_size
                    - num_inference_steps
                    - seed
                    - guidance_scale
                    - sync_mode
                    - num_images
                    - enable_safety_checker
                    - output_format
                    - negative_prompt
                    - nsfw_checker
                  x-apidog-ignore-properties: []
              x-apidog-orders:
                - model
                - callBackUrl
                - input
              x-apidog-ignore-properties: []
            example:
              model: qwen/image-edit
              callBackUrl: https://your-domain.com/api/callback
              input:
                prompt: ''
                image_url: >-
                  https://file.aiquickdraw.com/custom-page/akr/section-images/1755603225969i6j87xnw.jpg
                acceleration: none
                image_size: landscape_4_3
                num_inference_steps: 25
                guidance_scale: 4
                sync_mode: false
                enable_safety_checker: true
                output_format: png
                negative_prompt: blurry, ugly
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
                  taskId: task_qwen_1765179676651
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
      x-apidog-folder: docs/en/Market/Image    Models/Qwen
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/1184766/apis/api-28506382-run
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
