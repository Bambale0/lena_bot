# Wan 2.7 Image Pro

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
      summary: Wan 2.7 Image Pro
      deprecated: false
      description: >-
        Based on wan/2-7-image-pro, image generation and editing are achieved. 


        ## Query Task Status

        After submitting the task, you can check the progress of the task and
        obtain the generated results through the unified query endpoint: 


        <Card title="Get Task Details" icon="lucide-search"
        href="/market/common/get-task-detail"> 

        Learn how to check the task status and obtain the generated results

        </Card>


        ::: tip[]

        In the production environment, it is recommended to use the
        "callBackUrl" parameter to receive the automatic notification upon
        completion of the generation, rather than polling the status endpoint.

        :::


        Related resources

        <CardGroup cols={2}>
          <Card title="Market Overview" icon="lucide-store" href="/market/quickstart"> View all available models </Card>
          <Card title="General API" icon="lucide-cog" href="/common-api/get-account-credits"> View account credits and usage </Card>
        </CardGroup>
      tags:
        - docs/en/Market/Image    Models/Wan
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
                    - wan/2-7-image-pro
                  default: wan/2-7-image-pro
                  description: >-
                    Model name for generation tasks. This endpoint currently
                    uses `wan/2-7-image-pro`.
                  examples:
                    - wan/2-7-image-pro
                callBackUrl:
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
                  $ref: '#/components/schemas/CallbackUrl'
                input:
                  type: object
                  description: Input parameters for the generation task
                  properties:
                    prompt:
                      type: string
                      description: >-
                        Prompt for image generation or editing. This field
                        supports both Chinese and English, with a maximum length
                        of 5000 characters as per Alibaba Cloud documentation.
                      maxLength: 5000
                      examples:
                        - >-
                          Transform the food photo by replacing the marked
                          ingredients with sliced red chili pieces while
                          preserving the bowl, lighting, steam, camera angle,
                          and overall realism.
                    input_urls:
                      type: array
                      description: >-
                        (Optional) Array of input image URLs. The current
                        project uses `input_urls` as a wrapper field.
                      items:
                        type: string
                        format: uri
                      maxItems: 9
                      examples:
                        - - >-
                            https://static.aiquickdraw.com/tools/example/1775122744247_eSHwJX1k.jpg
                    aspect_ratio:
                      type: string
                      description: >-
                        (Optional) Output aspect ratio when no image input is
                        provided. 
                      examples:
                        - '1:1'
                      enum:
                        - '1:1'
                        - '16:9'
                        - '4:3'
                        - '21:9'
                        - '3:4'
                        - '9:16'
                        - '8:1'
                        - '1:8'
                      x-apidog-enum:
                        - value: '1:1'
                          name: ''
                          description: ''
                        - value: '16:9'
                          name: ''
                          description: ''
                        - value: '4:3'
                          name: ''
                          description: ''
                        - value: '21:9'
                          name: ''
                          description: ''
                        - value: '3:4'
                          name: ''
                          description: ''
                        - value: '9:16'
                          name: ''
                          description: ''
                        - value: '8:1'
                          name: ''
                          description: ''
                        - value: '1:8'
                          name: ''
                          description: ''
                    enable_sequential:
                      type: boolean
                      description: >-
                        Whether to enable sequential/group image mode. Default
                        is false.
                      default: false
                      examples:
                        - false
                    'n':
                      type: integer
                      description: >-
                        Number of images to generate. Range is 1-4 when
                        `enable_sequential=false` (default: 4); range is 1-12
                        when `enable_sequential=true` (default: 12).
                      examples:
                        - 4
                    resolution:
                      type: string
                      description: >-
                        Output resolution. The current project uses `resolution`
                        as a wrapper field corresponding to the underlying
                        resolution parameter.(4K generation is available only
                        for text-to-image in Standard Mode)
                      enum:
                        - 1K
                        - 2K
                        - 4K
                      default: 2K
                      examples:
                        - 2K
                    thinking_mode:
                      type: boolean
                      description: >-
                        Whether to enable thinking mode. Only available when
                        `enable_sequential=false` and `input_urls` is empty; the
                        frontend will automatically disable it in other cases.
                      default: false
                      examples:
                        - false
                    color_palette:
                      type: array
                      description: >-
                        (Optional) Custom color theme. Only available when
                        `enable_sequential=false`. Requires 3-10 colors, 8
                        recommended.
                      minItems: 3
                      maxItems: 10
                      items:
                        type: object
                        properties:
                          hex:
                            type: string
                            description: HEX color value.
                            pattern: ^#[0-9A-Fa-f]{6}$
                            examples:
                              - '#C2D1E6'
                          ratio:
                            type: string
                            description: Color proportion, format must be xx.xx%.
                            pattern: ^\d{1,3}\.\d{2}%$
                            examples:
                              - 23.51%
                        required:
                          - hex
                          - ratio
                        x-apidog-orders:
                          - hex
                          - ratio
                        x-apidog-ignore-properties: []
                    bbox_list:
                      type: array
                      description: >-
                        (Optional) Interactive editing bounding box areas. The
                        outer list length should match `input_urls`; maximum 2
                        boxes per image; single box format is `[x1, y1, x2,
                        y2]`.
                      items:
                        type: array
                        maxItems: 2
                        items:
                          type: array
                          minItems: 4
                          maxItems: 4
                          items:
                            type: integer
                      examples:
                        - - []
                    watermark:
                      type: boolean
                      description: Whether to add watermark.
                      default: false
                      examples:
                        - false
                    seed:
                      type: integer
                      description: Random seed, range 0-2147483647.
                      minimum: 0
                      maximum: 2147483647
                      default: 0
                      examples:
                        - 0
                    nsfw_checker:
                      type: boolean
                      description: >-
                        Defaults to false. You can set it to false based on your
                        needs. If set to false, our content filtering will be
                        disabled, and all results will be returned directly by
                        the model itself.
                      default: false
                  required:
                    - prompt
                  x-apidog-orders:
                    - prompt
                    - input_urls
                    - aspect_ratio
                    - enable_sequential
                    - 'n'
                    - resolution
                    - thinking_mode
                    - color_palette
                    - bbox_list
                    - watermark
                    - seed
                    - nsfw_checker
                  examples:
                    - prompt: >-
                        Transform the food photo by replacing the marked
                        ingredients with sliced red chili pieces in the
                        corresponding positions, while keeping the same bowl,
                        composition, steam, lighting, camera angle, background,
                        texture, and overall realism.
                      input_urls:
                        - >-
                          https://static.aiquickdraw.com/tools/example/1775122744247_eSHwJX1k.jpg
                      'n': 4
                      enable_sequential: false
                      resolution: 2K
                      thinking_mode: false
                      watermark: false
                      seed: 0
                      bbox_list:
                        - []
                  x-apidog-ignore-properties: []
              x-apidog-orders:
                - model
                - callBackUrl
                - input
              x-apidog-ignore-properties: []
            examples: {}
      responses:
        '200':
          description: ''
          content:
            application/json:
              schema:
                type: object
                properties:
                  code:
                    type: integer
                    description: >-
                      Response status code


                      - **200**: Success - Request has been processed
                      successfully

                      - **401**: Unauthorized - Authentication credentials are
                      missing or invalid

                      - **402**: Insufficient Credits - Account does not have
                      enough credits to perform the operation

                      - **404**: Not Found - The requested resource or endpoint
                      does not exist

                      - **422**: Validation Error - The request parameters
                      failed validation checks

                      - **429**: Rate Limited - Request limit has been exceeded
                      for this resource

                      - **433**: Request Limit - Sub-key Usage Exceeds Limit

                      - **455**: Service Unavailable - System is currently
                      undergoing maintenance

                      - **500**: Server Error - An unexpected error occurred
                      while processing the request

                      - **501**: Generation Failed - Content generation task
                      failed

                      - **505**: Feature Disabled - The requested feature is
                      currently disabled
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
                          Task ID, can be used with Get Task Details endpoint to
                          query task status
                    x-apidog-orders:
                      - taskId
                    required:
                      - taskId
                    x-apidog-ignore-properties: []
                x-apidog-orders:
                  - 01KN711JB7XC2YFEVAXJZZNXDZ
                required:
                  - data
                x-apidog-refs:
                  01KN711JB7XC2YFEVAXJZZNXDZ:
                    $ref: '#/components/schemas/ApiResponse'
                x-apidog-ignore-properties:
                  - code
                  - msg
                  - data
          headers: {}
          x-apidog-name: 成功
        '500':
          description: request failed
          content:
            application/json:
              schema:
                type: object
                properties:
                  code:
                    type: integer
                    description: >-
                      Response status code


                      - **200**: Success - Request has been processed
                      successfully

                      - **401**: Unauthorized - Authentication credentials are
                      missing or invalid

                      - **402**: Insufficient Credits - Account does not have
                      enough credits to perform the operation

                      - **404**: Not Found - The requested resource or endpoint
                      does not exist

                      - **408**: Upstream is currently experiencing service
                      issues. No result has been returned for over 10 minutes.

                      - **422**: Validation Error - The request parameters
                      failed validation checks

                      - **429**: Rate Limited - Request limit has been exceeded
                      for this resource

                      - **455**: Service Unavailable - System is currently
                      undergoing maintenance

                      - **500**: Server Error - An unexpected error occurred
                      while processing the request

                      - **501**: Generation Failed - Content generation task
                      failed

                      - **505**: Feature Disabled - The requested feature is
                      currently disabled
                  msg:
                    type: string
                    description: Response message, error description when failed
                  data:
                    type: object
                    properties: {}
                    x-apidog-orders: []
                    x-apidog-ignore-properties: []
                x-apidog-orders:
                  - code
                  - msg
                  - data
                required:
                  - code
                  - msg
                  - data
                x-apidog-ignore-properties: []
              example:
                code: 500
                msg: >-
                  Server Error - An unexpected error occurred while processing
                  the request
                data: null
          headers: {}
          x-apidog-name: 'Error '
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
      x-apidog-folder: docs/en/Market/Image    Models/Wan
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/1184766/apis/api-32370662-run
components:
  schemas:
    CallbackUrl:
      type: string
      format: uri
      description: >-
        The URL to receive generation task completion updates. Optional but
        recommended for production use.


        - System will POST task status and results to this URL when generation
        completes

        - Callback includes generated content URLs and task information

        - Your callback endpoint should accept POST requests with JSON payload
        containing results

        - Alternatively, use the Get Task Details endpoint to poll task status

        - To ensure callback security, see [Webhook Verification
        Guide](/common-api/webhook-verification) for signature verification
        implementation
      examples:
        - https://your-domain.com/api/callback
      x-apidog-folder: ''
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
