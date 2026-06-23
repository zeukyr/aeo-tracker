import { useState } from "react";
import { FilterContext } from "./FilterContext";

export function FilterProvider({ children }) {
  const [days, setDays] = useState(30);
  return (
    <FilterContext.Provider value={{ days, setDays }}>
      {children}
    </FilterContext.Provider>
  );
}