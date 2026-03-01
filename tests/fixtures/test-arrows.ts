export const fetchUsers = async (limit: number): Promise<string[]> => {
  return ['alice', 'bob'];
};

const validateEmail = (email: string): boolean => {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
};

export const processItems = (items: string[]) => {
  return items.filter(item => item.length > 0);
};

const double = (x: number) => x * 2;

var legacyHandler = (req: any) => {
  return req;
};

const namedFunc = function myFunc(x: number): number {
  return x + 1;
};

const anonFunc = function(x: number): number {
  return x + 1;
};

function regularFunction(name: string): string {
  return `Hello, ${name}`;
}
