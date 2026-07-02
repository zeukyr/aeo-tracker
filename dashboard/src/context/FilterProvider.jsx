import { useState } from "react";
import { FilterContext } from "./FilterContext";

export function FilterProvider({ children }) {
  const [days, setDays] = useState(30);
  const [school, setSchool] = useState("All");
  return (
    <FilterContext.Provider value={{ days, setDays, school, setSchool }}>
      {children}
    </FilterContext.Provider>
  );
}