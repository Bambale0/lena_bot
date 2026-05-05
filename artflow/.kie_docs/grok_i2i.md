# Grok Imagine - image to image

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
      summary: Grok Imagine - image to image
      deprecated: false
      description: >
        Content generation using grok-imagine/image-to-image


        ## File Upload Requirements


        Before using the Image-to-Image API, you need to upload your reference
        image:


        <Steps>

        <Step title="Upload Reference Image">
          Use the File Upload API to upload your reference image.

          <Card title="File Upload API" icon="lucide-upload" href="/file-upload-api/quickstart">
            Learn how to upload images and get file URLs
          </Card>

          **Requirements:**
          - **File Type**: JPEG, PNG, or WebP format
          - **Max File Size**: 10MB per file
          - **Content**: Image you want to use as reference for generation
        </Step>


        <Step title="Get File URL">
          After upload, you'll receive a file URL that you can use in the `image_urls` parameter.
        </Step>

        </Steps>


        <Warning>

        - Supported formats: JPEG, PNG, WebP (Max: 10MB)

        - Maximum one image per request

        </Warning>


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
      operationId: grok-imagine-image-to-image
      tags:
        - docs/en/Market/Image    Models/Grok Imagine
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
                    - grok-imagine/image-to-image
                  default: grok-imagine/image-to-image
                  description: |-
                    The model name to use for generation. Required field.

                    - Must be `grok-imagine/image-to-image` for this endpoint
                  examples:
                    - grok-imagine/image-to-image
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
                        A text description specifying the desired content or
                        style of the generated image. (Max length: 390000
                        characters)
                      type: string
                      maxLength: 390000
                      examples:
                        - >-
                          Recreate the Titanic movie poster with two adorable
                          anthropomorphic cats in the same romantic pose at the
                          bow of the ship. The male cat is an orange tabby
                          wearing a vest, standing behind a white long-haired
                          female cat in a lace dress, holding her paws as they
                          stretch forward in the wind. Both cats are
                          photorealistic with detailed fur, wind-swept hair, and
                          dramatic sunset lighting (warm golden highlights, cool
                          blue shadows). Background: the Titanic ship at dusk
                          with four smokestacks, glowing deck lights, calm
                          ocean, and orange-pink sunset sky. Center title:
                          “CATANIC” in the same gold metallic serif style as
                          Titanic, same size and position.
                    image_urls:
                      type: array
                      items:
                        type: string
                        format: uri
                      description: >-
                        An array containing up to 1 URL string pointing to
                        reference images. (Use file URLs after upload, not raw
                        file content. Accepted types: image/jpeg, image/png,
                        image/webp. Max size: 10.0MB per image.) In your prompt,
                        reference the uploaded image by typing @image(n)
                        followed by a space (for example: @image1 a sunset over
                        the ocean).
                      maxItems: 5
                      examples:
                        - - >-
                            https://static.aiquickdraw.com/tools/example/1767602105243_0MmMCrwq.png
                    nsfw_checker:
                      type: boolean
                      default: false
                      description: >-
                        Defaults to false. You can set it to false based on your
                        needs. If set to false, our content filtering will be
                        disabled, and all results will be returned directly by
                        the model itself.
                  required:
                    - image_urls
                  x-apidog-orders:
                    - prompt
                    - image_urls
                    - nsfw_checker
                  x-apidog-ignore-properties: []
              x-apidog-orders:
                - model
                - callBackUrl
                - input
              x-apidog-ignore-properties: []
            example:
              model: grok-imagine/image-to-image
              callBackUrl: https://your-domain.com/api/callback
              input:
                prompt: >-
                  Recreate the Titanic movie poster with two adorable
                  anthropomorphic cats in the same romantic pose at the bow of
                  the ship. The male cat is an orange tabby wearing a vest,
                  standing behind a white long-haired female cat in a lace
                  dress, holding her paws as they stretch forward in the wind.
                  Both cats are photorealistic with detailed fur, wind-swept
                  hair, and dramatic sunset lighting (warm golden highlights,
                  cool blue shadows). Background: the Titanic ship at dusk with
                  four smokestacks, glowing deck lights, calm ocean, and
                  orange-pink sunset sky. Center title: “CATANIC” in the same
                  gold metallic serif style as Titanic, same size and position.
                image_urls:
                  - >-
                    https://static.aiquickdraw.com/tools/example/1767602105243_0MmMCrwq.png
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
                  taskId: task_grok-imagine_1767694553297
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
      x-apidog-folder: docs/en/Market/Image    Models/Grok Imagine
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/1184766/apis/api-28506369-run
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
