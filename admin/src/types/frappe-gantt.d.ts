declare module 'frappe-gantt' {
  interface GanttTask {
    id: string
    name: string
    start: string
    end: string
    progress: number
    dependencies?: string
    custom_class?: string
  }

  interface GanttOptions {
    view_mode?: 'Day' | 'Week' | 'Month' | 'Year'
    date_format?: string
    readonly?: boolean
    language?: string
    on_click?: (task: GanttTask) => void
    on_date_change?: (task: GanttTask, start: Date, end: Date) => void
    on_progress_change?: (task: GanttTask, progress: number) => void
    on_view_change?: (mode: string) => void
    custom_popup_html?: (task: GanttTask) => string
  }

  class Gantt {
    constructor(element: string | HTMLElement, tasks: GanttTask[], options?: GanttOptions)
    change_view_mode(mode: 'Day' | 'Week' | 'Month' | 'Year'): void
    refresh(tasks: GanttTask[]): void
  }

  export default Gantt
  export type { GanttTask, GanttOptions }
}
