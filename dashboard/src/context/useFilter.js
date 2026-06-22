import { useContext } from "react";
import { FilterContext } from "./FilterContext";

export function useFilter() {
  return useContext(FilterContext);
}
