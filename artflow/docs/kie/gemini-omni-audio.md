# Gemini Omni Audio

## OpenAPI Specification

```yaml
openapi: 3.0.1
info:
  title: ''
  description: ''
  version: 1.0.0
paths:
  /api/v1/omni/audio/create:
    post:
      summary: Gemini Omni Audio
      deprecated: false
      description: |-
        ## Create Task

        Use this endpoint to create a new audio.

        ## Related Resources

        <CardGroup cols={2}>
          <Card title="Model Marketplace" icon="lucide-store" href="/market/quickstart">
            Explore all available models and capabilities
          </Card>
          <Card title="Common API" icon="lucide-cog" href="/common-api/get-account-credits">
            Check account credits and usage
          </Card>
        </CardGroup>
      operationId: gemini-omni-audio
      tags:
        - docs/en/Market/Video Models/Gemini Omni
      parameters: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              required:
                - audio_id
                - name
              properties:
                audio_id:
                  type: string
                  description: |-
                    Enum voice ID, used to select a preset voice character.
                     achernar - female, soft, high pitch 
                      achird - male, friendly, mid pitch 
                      algenib - male, raspy, low pitch 
                     algieba - male, easygoing, mid-low pitch  
                     alnilam - male, steady, mid-low pitch 
                     aoede - female, brisk, mid pitch 
                     autonoe - female, bright, mid pitch 
                     callirrhoe - female, easygoing, mid pitch 
                     charon - male, intellectual, low pitch 
                      despina - female, smooth, mid  pitch 
                     enceladus - male, breathy, low pitch 
                     erinome - female, clear, mid pitch 
                     fenrir -  male, lively, younger pitch 
                     gacrux - female, mature, mid pitch 
                     iapetus - male, clear, mid-low pitch 
                     kore - female, capable, mid pitch  
                      laomedeia - female, cheerful, mid-high pitch 
                     leda - female, young, mid-high pitch 
                     orus - male, steady, mid-low pitch 
                     puck - male, cheerful, mid pitch 
                     pulcherrima - genderless, forward, mid-high pitch 
                     rasalgethi - male, intellectual, mid pitch 
                     sadachbia -  male, vivid, low pitch 
                     sadaltager - male, knowledgeable, mid pitch 
                      schedar - male, smooth, mid-low pitch 
                     sulafat - female, warm, mid pitch 
                      umbriel - male, smooth, low pitch 
                      vindemiatrix - female, gentle, mid pitch 
                     zephyr - female, bright, mid-high pitch 
                     zubenelgenubi -   male, casual, mid-low pitch
                  examples:
                    - achernar
                    - achird
                    - algenib
                    - algieba
                    - alnilam
                    - aoede
                    - autonoe
                    - callirrhoe
                    - charon
                    - despina
                    - enceladus
                    - erinome
                    - fenrir
                    - gacrux
                    - iapetus
                    - kore
                    - laomedeia
                    - leda
                    - orus
                    - puck
                    - pulcherrima
                    - rasalgethi
                    - sadachbia
                    - sadaltager
                    - schedar
                    - sulafat
                    - umbriel
                    - vindemiatrix
                    - zephyr
                    - zubenelgenubi
                name:
                  type: string
                  description: 'Voice name. Maximum length: `210` characters.'
                voice_description:
                  type: string
                  description: >-
                    Voice characteristic description used to define timbre,
                    style, speaking rate, emotion, and other traits. Maximum
                    length: `20000` characters.
                example_dialogue:
                  type: string
                  description: >-
                    Example dialogue, such as "Hello, I am Adam". Maximum
                    length: `120` characters.
              x-apidog-orders:
                - audio_id
                - name
                - voice_description
                - example_dialogue
            example:
              audio_id: achernar
              name: achernar Narrator
              voice_description: >-
                A calm, clear, and friendly male voice suitable for tech
                explainers and daily conversation.
              example_dialogue: Hello, I am achernar
      responses:
        '200':
          description: Request successful
          content:
            application/json:
              schema:
                allOf:
                  - type: object
                    properties:
                      data:
                        type: object
                        properties:
                          kieAudioId:
                            type: string
                          name:
                            type: string
                        x-apidog-orders:
                          - kieAudioId
                          - name
                      msg:
                        type: string
                    x-apidog-orders:
                      - data
                      - msg
              example:
                code: 0
                msg: success
                data:
                  kieAudioId: a8f1c2d3e4f5...
                  name: gentle female voice
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
      x-apidog-folder: docs/en/Market/Video Models/Gemini Omni
      x-apidog-status: released
      x-run-in-apidog: https://app.apidog.com/web/project/1184766/apis/api-36213786-run
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
    BearerAuth1:
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
