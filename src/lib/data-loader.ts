import { load as parseYaml } from 'js-yaml'
import type { GameEvent } from '../types/events'
import { EventDataFileSchema } from '../types/events'

/**
 * 从 data/events/ 目录加载所有 YAML 活动数据文件
 *
 * 使用 Vite 的 import.meta.glob 在构建时静态分析，
 * 运行时按需加载原始文本，js-yaml 解析，Zod 校验。
 */
let cachedEvents: GameEvent[] | null = null

// Vite glob import: 匹配 data/events/ 下所有 .yaml 文件，以 raw 文本形式导入
const yamlModules = import.meta.glob('/data/events/*.yaml', {
  query: '?raw',
  import: 'default',
}) as Record<string, () => Promise<string>>

export async function loadAllEvents(): Promise<GameEvent[]> {
  if (cachedEvents) return cachedEvents

  const allEvents: GameEvent[] = []
  const errors: string[] = []

  for (const [filepath, loader] of Object.entries(yamlModules)) {
    try {
      const raw = await loader()
      const parsed = parseYaml(raw)

      const result = EventDataFileSchema.safeParse(parsed)
      if (!result.success) {
        const issues = result.error.issues
          .map((i) => `  ${i.path.join('.')}: ${i.message}`)
          .join('\n')
        console.error(`[data-loader] Schema error in ${filepath}:\n${issues}`)
        errors.push(filepath)
        continue
      }

      allEvents.push(...result.data)
    } catch (err) {
      console.error(`[data-loader] Failed to parse ${filepath}:`, err)
      errors.push(filepath)
    }
  }

  if (errors.length > 0) {
    console.warn(`[data-loader] ${errors.length} file(s) had errors, loaded ${allEvents.length} events total`)
  }

  cachedEvents = allEvents
  return cachedEvents
}

export function clearEventCache(): void {
  cachedEvents = null
}
