import { useEffect, useState } from 'react'
import dayjs from 'dayjs'

/** Keep an open dashboard on the current local day, including sleeping tabs. */
export function useLocalDate() {
  const [date, setDate] = useState(() => dayjs().format('YYYY-MM-DD'))
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>
    const update = () => {
      clearTimeout(timer)
      const now = dayjs()
      setDate(now.format('YYYY-MM-DD'))
      timer = setTimeout(update, now.add(1, 'day').startOf('day').valueOf() - now.valueOf() + 50)
    }
    update()
    window.addEventListener('focus', update)
    return () => { clearTimeout(timer); window.removeEventListener('focus', update) }
  }, [])
  return date
}
