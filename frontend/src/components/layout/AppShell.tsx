/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { motion, AnimatePresence } from 'motion/react';
import { useLocation } from 'react-router-dom';

export const AppShell: React.FC = () => {
  const location = useLocation();

  return (
    <div className="min-h-screen bg-[#0F0F0F] text-[#F5F5F5] font-sans">
      <Sidebar />
      <main className="pl-[220px] min-h-screen">
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.1 }}
            className="p-8"
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
};
