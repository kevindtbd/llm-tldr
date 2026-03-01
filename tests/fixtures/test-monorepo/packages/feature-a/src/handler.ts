import { helper, validateEmail } from '@shared';
import { formatDate } from '@shared/format';

export const processRequest = async (data: { email: string; date: Date }) => {
  const cleaned = helper(data.email);
  const isValid = validateEmail(cleaned);
  const dateStr = formatDate(data.date);

  return { cleaned, isValid, dateStr };
};

const internalHelper = (x: number) => x * 2;

export default (req: Request, res: Response) => {
  res.json({ ok: true });
};
