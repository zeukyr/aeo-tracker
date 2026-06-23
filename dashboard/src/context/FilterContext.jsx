import { createContext, useContext, useState } from "react";

const FilterContext = createContext();

export const PERIOD_OPTIONS = [
  { label: "7 days", value: 7 },
  { label: "30 days", value: 30 },
  { label: "90 days", value: 90 },
];

export function FilterProvider({ children }) {
  const [days, setDays] = useState(30);
  return (
    <FilterContext.Provider value={{ days, setDays }}>
      {children}
    </FilterContext.Provider>
  );
}

export function useFilter() {
  return useContext(FilterContext);
}
