import { createContext, useState } from "react";

const FilterContext = createContext();

export function FilterProvider({ children }) {
  const [days, setDays] = useState(30);
  return (
    <FilterContext.Provider value={{ days, setDays }}>
      {children}
    </FilterContext.Provider>
  );
}
