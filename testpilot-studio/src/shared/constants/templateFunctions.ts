export type BuiltinTemplateFunction = {
  token: string
  label: string
  description: string
  example?: string
}

export const builtinTemplateFunctions: BuiltinTemplateFunction[] = [
  { token: '{{$timestamp}}', label: '$timestamp', description: '秒级时间戳', example: '{{$timestamp}}' },
  { token: '{{$timestamp_ms}}', label: '$timestamp_ms', description: '毫秒级时间戳', example: '{{$timestamp_ms}}' },
  { token: '{{$now}}', label: '$now', description: '当前时间 RFC3339 字符串', example: '{{$now}}' },
  {
    token: '{{$date "2006-01-02 15:04:05"}}',
    label: '$date',
    description: '按格式输出当前时间，需要 1 个带引号的格式参数',
    example: '{{$date "2006-01-02"}}',
  },
  { token: '{{$uuid}}', label: '$uuid', description: '生成 UUID', example: '{{$uuid}}' },
  {
    token: '{{$randomInt 1000 9999}}',
    label: '$randomInt',
    description: '生成随机整数，需要 2 个整数参数',
    example: '{{$randomInt 1 9}}',
  },
  {
    token: '{{$randomString 8}}',
    label: '$randomString',
    description: '生成随机字符串，需要 1 个整数参数',
    example: '{{$randomString 8}}',
  },
]

export const uiBuiltinTemplateFunctions: BuiltinTemplateFunction[] = [
  builtinTemplateFunctions[0],
  builtinTemplateFunctions[1],
  {
    token: '{{$date "2006-01-02"}}',
    label: '$date',
    description: '按格式输出当前日期，UI 执行器支持带引号的格式参数',
    example: '{{$date "2006-01-02"}}',
  },
  builtinTemplateFunctions[4],
  builtinTemplateFunctions[5],
  builtinTemplateFunctions[6],
]
