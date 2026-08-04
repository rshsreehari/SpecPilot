import type { QuestionRecord } from '../lib/types'
import './QuestionTable.css'

/** Mirrors the backend's own mechanical grading signal (src/eval/grade.py's
 * expected_endpoints_covered) rather than re-deriving correctness in the UI - "all
 * expected endpoints were among the ones graded" already accounts for correct
 * refusals, since an unanswerable question has zero expected endpoints. */
function isCorrect(record: QuestionRecord): boolean {
  return (record.expected_endpoints_covered ?? 0) === record.expected_endpoints.length
}

export function QuestionTable({ questions }: { questions: QuestionRecord[] }) {
  return (
    <div className="question-table-wrap">
      <table className="question-table">
        <thead>
          <tr>
            <th scope="col">ID</th>
            <th scope="col">Category</th>
            <th scope="col">Mode</th>
            <th scope="col">Question</th>
            <th scope="col">Result</th>
            <th scope="col">Latency</th>
          </tr>
        </thead>
        <tbody>
          {questions.map((record) => (
            <tr key={`${record.question_id}-${record.mode}`}>
              <td className="question-table-mono">{record.question_id}</td>
              <td>{record.category}</td>
              <td>{record.mode}</td>
              <td className="question-table-question">{record.question}</td>
              <td>
                <span className="question-table-badge" data-ok={isCorrect(record)}>
                  {record.refused
                    ? isCorrect(record)
                      ? 'correct refusal'
                      : 'wrong refusal'
                    : isCorrect(record)
                      ? 'correct'
                      : 'wrong'}
                </span>
              </td>
              <td>{Math.round(record.latency_ms)}ms</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
