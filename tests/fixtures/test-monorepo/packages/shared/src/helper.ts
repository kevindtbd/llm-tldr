export const helper = (input: string): string => {
  return input.trim().toLowerCase();
};

export const validateEmail = (email: string): boolean => {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
};
