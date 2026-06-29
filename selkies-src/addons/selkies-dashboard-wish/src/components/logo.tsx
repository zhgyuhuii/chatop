import * as React from "react";

// Selkies Logo Component - 使用 logo.png
export const SelkiesLogo = ({ width = 30, height = 30, className = "", ...props }: { width?: number; height?: number; className?: string;[key: string]: any }) => (
  <img src="logo.png" width={width} height={height} className={className} alt="Logo" {...props} />
);