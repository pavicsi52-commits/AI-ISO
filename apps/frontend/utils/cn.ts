/**
 * Joins conditional class names. A minimal, dependency-free alternative to
 * `clsx` — kept in-house since the frontend stack is frozen per
 * docs/003_Technology_Stack_Master.md.txt and does not list a class-name
 * utility library.
 */
export type ClassValue = string | number | null | undefined | false | ClassValue[];

export function cn(...values: ClassValue[]): string {
  const classes: string[] = [];

  for (const value of values) {
    if (!value) continue;
    if (Array.isArray(value)) {
      const nested = cn(...value);
      if (nested) classes.push(nested);
      continue;
    }
    classes.push(String(value));
  }

  return classes.join(" ");
}
