'use client'

import { useState } from 'react'
import Link from 'next/link'
import {
  Printer,
  Download,
  ArrowLeft,
  Copy,
  Check,
  ShieldCheck,
  AlertTriangle,
  Fingerprint,
  Clock,
  Zap,
} from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function ExportReportPage() {
  const [copied, setCopied] = useState(false)

  const handlePrint = () => {
    window.print()
  }

  const handleCopySummary = () => {
    const summary = `SENTINEL v2.4 CCTV AUDIT & FACE RECOGNITION REPORT (DBGT POC)
Report ID: SENTINEL-EVAL-DBGT-20261017-01
Client: Dakshin Bharat Gateway Terminal (DBGT)
Location: Camera-1 (Terminal Gate Ch4)
Date: 17 Oct 2026

1. CCTV CONTINUITY & MISSING FOOTAGE FINDINGS:
   - 🔴 7-Hour Overnight Blackout: 7h 02m 25s missing (01:58 AM - 08:59 AM).
   - 🟡 1.7-Minute Video Cut: 101 seconds cut inside the morning recording.
   - Digital Fingerprints (SHA-256): Verified authentic for all source video files.

2. FACE RECOGNITION & STAFF ATTENDANCE:
   - Total Face Sightings: 59 appearances
   - Unique People Identified: 3 staff members (0 duplicate confusion)
     • Jenisha (Management / VIP): 28 sightings | 09:09 AM - 09:43 AM (33m stay) | 82.1% Match
     • Selvi (Staff Member): 16 sightings | 09:10 AM - 09:58 AM (48m stay) | 91.1% Match
     • Pravin (Staff Member): 15 sightings | 09:08 AM - 09:49 AM (40m stay) | 88.5% Match

3. SPEED & SYSTEM PERFORMANCE:
   - Speed: 11.2 FPS (~15x faster than real-time playback).
   - Smart Motion Filter: Automatically skipped 89.6% of empty frames (saved 712 empty checks).
   - Runs on standard office CPU hardware without requiring expensive graphics servers.`
    navigator.clipboard.writeText(summary)
    setCopied(true)
    setTimeout(() => setCopied(false), 2500)
  }

  return (
    <div className="min-h-screen bg-slate-900 text-slate-900 print:bg-white print:text-slate-900 antialiased">
      {/* Top Floating Control Bar (Hidden when printing) */}
      <nav className="print:hidden sticky top-0 z-50 border-b border-slate-700 bg-slate-900/95 px-4 py-3 backdrop-blur-md text-white shadow-xl">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/">
              <Button variant="ghost" size="sm" className="h-8 gap-1.5 text-xs text-slate-300 hover:text-white hover:bg-slate-800">
                <ArrowLeft className="size-3.5" />
                <span>Back to Dashboard</span>
              </Button>
            </Link>
            <div className="h-4 w-px bg-slate-700" />
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-bold text-amber-400">DBGT POC Demo Report</span>
              <span className="rounded bg-emerald-500/20 px-2 py-0.5 text-[10px] font-semibold text-emerald-300 border border-emerald-500/30">
                Client Ready (Plain English)
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleCopySummary}
              className="h-8 gap-1.5 text-xs border-slate-700 text-slate-200 hover:bg-slate-800"
            >
              {copied ? <Check className="size-3.5 text-emerald-400" /> : <Copy className="size-3.5" />}
              <span>{copied ? 'Copied' : 'Copy Summary'}</span>
            </Button>

            <a
              href="/reports/DBGT_CCTV_Security_Audit_Report.pdf"
              download="DBGT_CCTV_Security_Audit_Report.pdf"
              className="inline-flex items-center"
            >
              <Button
                variant="outline"
                size="sm"
                className="h-8 gap-1.5 text-xs border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20 hover:text-emerald-200"
              >
                <Download className="size-3.5" />
                <span>Download PDF</span>
              </Button>
            </a>

            <Button
              size="sm"
              onClick={handlePrint}
              className="h-8 gap-1.5 text-xs font-semibold bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-600 hover:to-amber-700 text-black shadow-lg shadow-amber-500/20 cursor-pointer"
            >
              <Printer className="size-3.5" />
              <span>Print / Save as A4 PDF</span>
            </Button>
          </div>
        </div>
      </nav>

      {/* Embedded Print Styling */}
      <style
        dangerouslySetInnerHTML={{
          __html: `
        @media print {
          @page {
            size: A4 portrait;
            margin: 10mm 12mm 10mm 12mm;
          }
          html, body {
            background-color: #ffffff !important;
            color: #0f172a !important;
            font-size: 11px !important;
            line-height: 1.35 !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
          }
          .page-break {
            page-break-before: always !important;
            break-before: page !important;
          }
          .avoid-break {
            page-break-inside: avoid !important;
            break-inside: avoid !important;
          }
        }
      `,
        }}
      />

      {/* Main 2-Page Document Container */}
      <main className="mx-auto max-w-4xl p-4 sm:p-8 print:p-0 print:max-w-none">
        
        {/* ========================================================================= */}
        {/* PAGE 1: CCTV INTEGRITY, MISSING FOOTAGE AUDIT & TIMELINE MAP              */}
        {/* ========================================================================= */}
        <section className="bg-white text-slate-900 rounded-xl p-8 sm:p-10 shadow-2xl print:shadow-none print:p-0 print:border-none border border-slate-200 mb-8 print:mb-0">
          
          {/* Header Strip */}
          <div className="border-b-2 border-slate-900 pb-3 mb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] font-bold uppercase tracking-wider text-amber-700">
                  SENTINEL v2.4 CCTV INTELLIGENCE
                </span>
                <span className="text-slate-400">•</span>
                <span className="font-mono text-[10px] font-bold text-emerald-800 uppercase bg-emerald-100 border border-emerald-300 px-1.5 py-0.5 rounded">
                  CLIENT POC DEMO REPORT
                </span>
              </div>
              <div className="font-mono text-[10px] text-slate-600 font-semibold">
                CONFIDENTIAL // PREPARED FOR DBGT
              </div>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-950 mt-1">
              CCTV Video Verification & Security Audit Report
            </h1>
            <p className="text-xs text-slate-600 mt-0.5">
              Automated Missing Footage Detection, Video Tamper Verification & Staff Attendance Summary
            </p>
          </div>

          {/* Quick Info Box */}
          <div className="mb-3 overflow-hidden rounded-md border border-slate-300 bg-slate-50 text-[11px]">
            <table className="w-full text-left">
              <tbody className="divide-y divide-slate-200">
                <tr className="divide-x divide-slate-200">
                  <td className="w-1/4 p-1.5 font-bold text-slate-700 bg-slate-100">Client / Facility</td>
                  <td className="w-1/4 p-1.5 font-semibold text-slate-900">Dakshin Bharat Gateway Terminal (DBGT)</td>
                  <td className="w-1/4 p-1.5 font-bold text-slate-700 bg-slate-100">Report Date</td>
                  <td className="w-1/4 p-1.5 font-mono text-slate-900">17 October 2026</td>
                </tr>
                <tr className="divide-x divide-slate-200">
                  <td className="p-1.5 font-bold text-slate-700 bg-slate-100">Camera Location</td>
                  <td className="p-1.5 text-slate-900">Camera-1 (Terminal Gate Ch4)</td>
                  <td className="p-1.5 font-bold text-slate-700 bg-slate-100">Audit Scope</td>
                  <td className="p-1.5 text-emerald-800 font-semibold">Footage Continuity & Gate Attendance POC</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* 4 Big Traffic Light Scorecards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
            <div className="p-2.5 rounded-lg border border-red-300 bg-red-50">
              <span className="text-[10px] font-bold text-red-700 block uppercase">Missing Video Alert</span>
              <span className="text-lg font-bold text-red-950 block leading-tight">7h 02m Missing</span>
              <span className="text-[10px] text-slate-600">Overnight Blackout Gap</span>
            </div>
            <div className="p-2.5 rounded-lg border border-amber-300 bg-amber-50">
              <span className="text-[10px] font-bold text-amber-700 block uppercase">Video Cut Alert</span>
              <span className="text-lg font-bold text-amber-950 block leading-tight">101s Cut Inside</span>
              <span className="text-[10px] text-slate-600">Morning Clip Spliced/Cut</span>
            </div>
            <div className="p-2.5 rounded-lg border border-emerald-300 bg-emerald-50">
              <span className="text-[10px] font-bold text-emerald-700 block uppercase">People Detected</span>
              <span className="text-lg font-bold text-emerald-950 block leading-tight">3 Staff Verified</span>
              <span className="text-[10px] text-slate-600">0 Unknown Intruders</span>
            </div>
            <div className="p-2.5 rounded-lg border border-blue-300 bg-blue-50">
              <span className="text-[10px] font-bold text-blue-700 block uppercase">Investigation Speed</span>
              <span className="text-lg font-bold text-blue-950 block leading-tight">15× Real-Time</span>
              <span className="text-[10px] text-slate-600">1 Hr Video in 5 Minutes</span>
            </div>
          </div>

          {/* 1. What Did We Test? (Executive Summary in Plain English) */}
          <div className="mb-3.5 avoid-break">
            <h2 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-900 border-b border-slate-300 pb-1 mb-1.5">
              1. What Did We Test? (Purpose of this Evaluation)
            </h2>
            <p className="text-[11px] text-slate-700 leading-relaxed mb-2">
              We connected Sentinel to raw CCTV recordings from <strong>Terminal Gate Channel 4</strong>. In standard security operations, if a camera stops recording or someone deletes overnight footage, regular video players play files one after another without warning you. Sentinel audits every second of the timeline and scans for people automatically:
            </p>

            {/* VISUAL EXAMPLE 1: Visual Timeline Bar */}
            <div className="rounded-lg border border-slate-300 bg-slate-950 p-2.5 text-white mb-3">
              <div className="flex justify-between items-center text-[10px] font-mono mb-1.5 text-slate-300">
                <span className="font-bold text-amber-400 uppercase">Visual Proof: CCTV Recording Continuity Timeline (00:00 - 10:00 IST)</span>
                <span>Total Recorded: 1h 58m | Missing: 7h 02m</span>
              </div>
              
              {/* Graphic Timeline Bar */}
              <div className="w-full h-8 rounded bg-slate-900 border border-slate-800 flex overflow-hidden text-[9px] font-bold">
                {/* 00:00 to 00:58 (Prior) */}
                <div className="w-[10%] bg-slate-800 text-slate-400 flex items-center justify-center border-r border-slate-700">
                  Prior
                </div>
                {/* 00:58 to 01:58 (Clip 1) */}
                <div className="w-[10%] bg-emerald-600 text-white flex flex-col items-center justify-center border-r border-slate-700 shadow-inner">
                  <span className="text-[8.5px]">Clip 1: OK</span>
                  <span className="text-[7.5px] opacity-80">00:58-01:58</span>
                </div>
                {/* 01:58 to 08:59 (7h Blackout Gap) */}
                <div className="w-[70%] bg-red-600/90 text-white flex flex-col items-center justify-center border-r border-slate-700 shadow-inner px-1 relative overflow-hidden">
                  <div className="absolute inset-0 bg-[linear-gradient(45deg,rgba(0,0,0,0.15)_25%,transparent_25%,transparent_50%,rgba(0,0,0,0.15)_50%,rgba(0,0,0,0.15)_75%,transparent_75%,transparent)] bg-[length:12px_12px]" />
                  <span className="relative z-10 text-[9px] font-black tracking-wide text-white drop-shadow">
                    ⚠️ [CRITICAL BLACKOUT] 7 HOURS 2 MINUTES MISSING FOOTAGE
                  </span>
                  <span className="relative z-10 text-[7.5px] text-red-100">
                    Camera Powered Off or Recordings Deleted (01:58 AM - 08:59 AM)
                  </span>
                </div>
                {/* 08:59 to 09:59 (Clip 2) */}
                <div className="w-[10%] bg-emerald-600 text-white flex flex-col items-center justify-center relative shadow-inner">
                  <div className="absolute top-0 right-3 bottom-0 w-1.5 bg-amber-400" title="101s Cut at 09:34" />
                  <span className="text-[8.5px]">Clip 2: OK</span>
                  <span className="text-[7.5px] opacity-80">08:59-09:59</span>
                </div>
              </div>

              <div className="flex justify-between items-center text-[8.5px] text-slate-400 mt-1 font-mono">
                <span>00:00 IST</span>
                <span>02:00 IST</span>
                <span>04:00 IST</span>
                <span>06:00 IST</span>
                <span>08:00 IST</span>
                <span>10:00 IST</span>
              </div>
            </div>

            {/* The 2 Key Security Findings */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[10.5px] mb-2.5">
              <div className="rounded border border-red-300 bg-red-50 p-2.5">
                <div className="flex items-center gap-1 font-bold text-red-800 mb-0.5">
                  <AlertTriangle className="size-3.5 text-red-600 shrink-0" />
                  <span>Alert 1: 7-Hour Overnight Blackout (01:58 AM - 08:59 AM)</span>
                </div>
                <p className="text-slate-800 text-[10px] leading-relaxed">
                  The camera stopped recording at <strong>01:58:53 AM</strong> and only resumed at <strong>08:59:37 AM</strong>. A total of <strong>7 hours, 2 minutes, and 25 seconds of video are missing completely</strong>. Total coverage was only <strong>21.9%</strong>.
                  <br />
                  <span className="text-slate-600 italic">Security Action: Inspect camera power supply and check if midnight shift recorder disk ran out of space.</span>
                </p>
              </div>

              <div className="rounded border border-amber-300 bg-amber-50 p-2.5">
                <div className="flex items-center gap-1 font-bold text-amber-800 mb-0.5">
                  <Fingerprint className="size-3.5 text-amber-600 shrink-0" />
                  <span>Alert 2: 1.7-Minute Internal Video Cut (101s Missing)</span>
                </div>
                <p className="text-slate-800 text-[10px] leading-relaxed">
                  Inside the morning video (Clip 02), our system detected a <strong>101-second sudden jump</strong> in the video timeline.
                  <br />
                  <span className="text-slate-600 italic">Security Action: Proves that recording paused or video was edited. Flagged for shift review.</span>
                </p>
              </div>
            </div>

            {/* SCREENSHOT 1: Red Alert Banner Crop */}
            <div className="rounded border border-slate-300 overflow-hidden bg-slate-950 p-1 mb-2">
              <img
                src="/reports/screenshot_1_continuity_alert.png"
                alt="Security Alert Banner and Continuity Metrics"
                className="w-full max-h-20 sm:max-h-24 object-contain rounded"
              />
              <div className="text-[8.5px] font-mono text-slate-300 px-1 py-0.5 flex justify-between bg-slate-900 border-t border-slate-800">
                <span><strong>Figure 1:</strong> Sentinel Live Dashboard Warning — 7h 2m 25s Missing Gap & 21.9% Continuity Alert</span>
                <span className="text-red-400 font-bold">Critical Alert Verified</span>
              </div>
            </div>

            {/* Comparison Table: Sentinel vs Standard CCTV */}
            <table className="w-full text-left text-[9.5px] border border-slate-300 rounded overflow-hidden">
              <thead className="bg-slate-100 font-semibold text-slate-700 border-b border-slate-300">
                <tr>
                  <th className="p-1.5 border-r border-slate-300 w-1/4">Security Parameter</th>
                  <th className="p-1.5 border-r border-slate-300 w-1/4">Sentinel Automated Audit</th>
                  <th className="p-1.5 border-r border-slate-300 w-1/4">Standard CCTV / Manual Review</th>
                  <th className="p-1.5 w-1/4">Value to DBGT Security</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                <tr>
                  <td className="p-1.5 font-semibold text-slate-900 border-r border-slate-200">Missing Video Detection</td>
                  <td className="p-1.5 font-bold text-red-700 border-r border-slate-200">Found 2 Gaps (7h blackout + 101s cut)</td>
                  <td className="p-1.5 text-slate-600 border-r border-slate-200">Skips missing time silently</td>
                  <td className="p-1.5 font-medium text-slate-800">Immediate proof if video is deleted or lost</td>
                </tr>
                <tr>
                  <td className="p-1.5 font-semibold text-slate-900 border-r border-slate-200">Investigation Speed</td>
                  <td className="p-1.5 font-bold text-emerald-700 border-r border-slate-200">15× Real-Time (1 hr in 5 mins)</td>
                  <td className="p-1.5 text-slate-600 border-r border-slate-200">1× (Must watch hour by hour)</td>
                  <td className="p-1.5 font-medium text-slate-800">Audits 24 hours of video in under 2 hours</td>
                </tr>
                <tr>
                  <td className="p-1.5 font-semibold text-slate-900 border-r border-slate-200">Empty Footage Filter</td>
                  <td className="p-1.5 font-bold text-emerald-700 border-r border-slate-200">89.6% empty frames skipped</td>
                  <td className="p-1.5 text-slate-600 border-r border-slate-200">Guards watch blank walls for hours</td>
                  <td className="p-1.5 font-medium text-slate-800">Guards only review footage when people appear</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Page 1 Footer */}
          <div className="pt-2 border-t border-slate-300 flex justify-between items-center text-[8.5px] font-mono text-slate-500">
            <span>SENTINEL-EVAL-DBGT-20261017-01</span>
            <span>CCTV SECURITY AUDIT — CONFIDENTIAL // FOR DBGT INTERNAL USE ONLY</span>
            <span>Page 1 of 2</span>
          </div>
        </section>


        {/* ========================================================================= */}
        {/* PAGE 2: GATE ATTENDANCE, FACIAL RECOGNITION & STAFF DOSSIER               */}
        {/* ========================================================================= */}
        <section className="page-break bg-white text-slate-900 rounded-xl p-8 sm:p-10 shadow-2xl print:shadow-none print:p-0 print:border-none border border-slate-200">
          
          {/* Page 2 Top Header Strip */}
          <div className="border-b border-slate-300 pb-2 mb-3 flex justify-between items-center text-[9.5px] font-mono text-slate-600">
            <span className="font-bold text-amber-700">SENTINEL v2.4 • DBGT PORT TERMINAL</span>
            <span>SECTION 2: GATE ATTENDANCE & PEOPLE RECOGNITION</span>
            <span className="font-semibold text-slate-900">Page 2 of 2</span>
          </div>

          {/* 2. Who Was Present at the Gate? */}
          <div className="mb-3.5 avoid-break">
            <div className="flex items-center justify-between mb-1">
              <h2 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-900">
                2. Who Was Present at the Gate & How Long Did They Stay?
              </h2>
              <span className="font-mono text-[9px] bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded border border-emerald-300 font-semibold">
                Smart Grouping: Zero False Duplicate Alarms
              </span>
            </div>
            
            <p className="text-[10.5px] text-slate-700 leading-relaxed mb-2">
              In 1 hour of morning footage, the camera detected faces <strong>59 times</strong>. Standard CCTV systems would falsely sound 59 separate alarms. Sentinel automatically grouped all sightings into the <strong>exact 3 verified staff members</strong>, giving accurate entry times, exit times, and stay durations:
            </p>

            {/* VISUAL EXAMPLE 2: 3-Step Flow Diagram */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-2.5">
              <div className="p-2 rounded border border-slate-200 bg-slate-50 text-[9.5px]">
                <span className="font-bold text-slate-900 block mb-0.5 uppercase text-[9px] text-slate-600">Step 1: Motion Filter</span>
                <p className="text-slate-700 leading-tight">
                  Skips empty hallways automatically.
                  <br />
                  <strong className="text-emerald-700">→ 89.6% empty video bypassed</strong>
                </p>
              </div>

              <div className="p-2 rounded border border-slate-200 bg-slate-50 text-[9.5px]">
                <span className="font-bold text-slate-900 block mb-0.5 uppercase text-[9px] text-slate-600">Step 2: Face Scanner</span>
                <p className="text-slate-700 leading-tight">
                  Takes high-speed face crops when person enters.
                  <br />
                  <strong className="text-blue-700">→ Found 59 face sightings</strong>
                </p>
              </div>

              <div className="p-2 rounded border border-emerald-300 bg-emerald-50 text-[9.5px]">
                <span className="font-bold text-emerald-900 block mb-0.5 uppercase text-[9px] text-emerald-700">Step 3: Smart Grouping</span>
                <p className="text-emerald-900 leading-tight">
                  No duplicate alarms for the same person.
                  <br />
                  <strong className="text-emerald-800">→ Exactly 3 Real People</strong>
                </p>
              </div>
            </div>

            {/* People Table */}
            <table className="w-full text-left text-[9.5px] border border-slate-300 rounded mb-2 overflow-hidden">
              <thead className="bg-slate-100 font-semibold text-slate-700 border-b border-slate-300">
                <tr>
                  <th className="p-1.5 border-r border-slate-300">#</th>
                  <th className="p-1.5 border-r border-slate-300">Identified Person</th>
                  <th className="p-1.5 border-r border-slate-300">Company Role</th>
                  <th className="p-1.5 border-r border-slate-300">Sightings</th>
                  <th className="p-1.5 border-r border-slate-300">First In</th>
                  <th className="p-1.5 border-r border-slate-300">Last Out</th>
                  <th className="p-1.5 border-r border-slate-300">Time in Area</th>
                  <th className="p-1.5 border-r border-slate-300">Match Accuracy</th>
                  <th className="p-1.5">Activity at Gate</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                <tr>
                  <td className="p-1.5 font-mono font-bold text-slate-900 border-r border-slate-200">01</td>
                  <td className="p-1.5 font-bold text-slate-950 border-r border-slate-200">Jenisha</td>
                  <td className="p-1.5 border-r border-slate-200"><span className="bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded text-[8.5px] font-bold">Management / VIP</span></td>
                  <td className="p-1.5 font-mono font-bold text-emerald-700 border-r border-slate-200">28 times</td>
                  <td className="p-1.5 font-mono border-r border-slate-200">09:09 AM</td>
                  <td className="p-1.5 font-mono border-r border-slate-200">09:43 AM</td>
                  <td className="p-1.5 font-bold text-slate-900 border-r border-slate-200">33 mins</td>
                  <td className="p-1.5 font-mono font-bold text-emerald-700 border-r border-slate-200">82.1%</td>
                  <td className="p-1.5 text-slate-700">Walked through gate across 4 episodes</td>
                </tr>
                <tr>
                  <td className="p-1.5 font-mono font-bold text-slate-900 border-r border-slate-200">02</td>
                  <td className="p-1.5 font-bold text-slate-950 border-r border-slate-200">Selvi</td>
                  <td className="p-1.5 border-r border-slate-200"><span className="bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded text-[8.5px] font-bold">Terminal Staff</span></td>
                  <td className="p-1.5 font-mono font-bold text-emerald-700 border-r border-slate-200">16 times</td>
                  <td className="p-1.5 font-mono border-r border-slate-200">09:10 AM</td>
                  <td className="p-1.5 font-mono border-r border-slate-200">09:58 AM</td>
                  <td className="p-1.5 font-bold text-slate-900 border-r border-slate-200">48 mins</td>
                  <td className="p-1.5 font-mono font-bold text-emerald-700 border-r border-slate-200">91.1%</td>
                  <td className="p-1.5 text-slate-700">Stationary & active in area entire hour</td>
                </tr>
                <tr>
                  <td className="p-1.5 font-mono font-bold text-slate-900 border-r border-slate-200">03</td>
                  <td className="p-1.5 font-bold text-slate-950 border-r border-slate-200">Pravin</td>
                  <td className="p-1.5 border-r border-slate-200"><span className="bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded text-[8.5px] font-bold">Terminal Staff</span></td>
                  <td className="p-1.5 font-mono font-bold text-emerald-700 border-r border-slate-200">15 times</td>
                  <td className="p-1.5 font-mono border-r border-slate-200">09:08 AM</td>
                  <td className="p-1.5 font-mono border-r border-slate-200">09:49 AM</td>
                  <td className="p-1.5 font-bold text-slate-900 border-r border-slate-200">40 mins</td>
                  <td className="p-1.5 font-mono font-bold text-emerald-700 border-r border-slate-200">88.5%</td>
                  <td className="p-1.5 text-slate-700">Frequent gate entrance & exit passage</td>
                </tr>
              </tbody>
            </table>

            {/* SCREENSHOT 5: The 3 Subject Cards Crop */}
            <div className="rounded border border-slate-300 overflow-hidden bg-slate-950 p-1 mb-2">
              <img
                src="/reports/screenshot_5_subject_cards.png"
                alt="Subject Sightings and Trajectory Table"
                className="w-full max-h-24 sm:max-h-28 object-contain rounded"
              />
              <div className="text-[8.5px] font-mono text-slate-300 px-1 py-0.5 flex justify-between bg-slate-900 border-t border-slate-800">
                <span><strong>Figure 2:</strong> Live Sentinel Identity Cards — Photos, Time Ranges, and Match Confidence Meters for Jenisha, Pravin, and Selvi</span>
                <span className="text-emerald-400 font-bold">Verified Identity Profiles</span>
              </div>
            </div>
          </div>

          {/* 3. Processing Speed & Cost Efficiency */}
          <div className="mb-3.5 avoid-break">
            <h2 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-900 border-b border-slate-300 pb-1 mb-1.5">
              3. Processing Speed & Hardware Efficiency
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[10px] mb-2">
              <div className="p-2 rounded border border-slate-200 bg-slate-50">
                <div className="flex items-center gap-1.5 font-bold text-slate-900 mb-0.5">
                  <Zap className="size-3.5 text-amber-600" />
                  <span>Ultra-Fast Processing (15× Real-Time)</span>
                </div>
                <p className="text-slate-700 leading-relaxed text-[9.5px]">
                  Processed <strong>11.2 frames per second</strong> on standard computer hardware. A full 1-hour CCTV recording was audited in <strong>less than 5 minutes</strong>, saving over 90% of manual investigation time.
                </p>
              </div>
              <div className="p-2 rounded border border-slate-200 bg-slate-50">
                <div className="flex items-center gap-1.5 font-bold text-slate-900 mb-0.5">
                  <Clock className="size-3.5 text-emerald-600" />
                  <span>Smart Motion Filter (89.6% Empty Footage Skipped)</span>
                </div>
                <p className="text-slate-700 leading-relaxed text-[9.5px]">
                  Out of 799 sample frames, <strong>712 empty frames</strong> with zero movement were skipped automatically. The AI concentrated 100% of its power only on moments when people were on screen.
                </p>
              </div>
            </div>
          </div>

          {/* 4. Conclusion & Takeaways for DBGT Management */}
          <div className="pt-2 border-t-2 border-slate-900 avoid-break">
            <div className="flex items-center gap-1.5 mb-1">
              <ShieldCheck className="size-4 text-emerald-700" />
              <h2 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-950">
                4. Conclusion & Executive Takeaways for DBGT Management
              </h2>
            </div>
            
            <p className="text-[9.5px] text-slate-700 mb-2 leading-relaxed">
              <strong>1. Zero Blind Spots:</strong> Immediately alerts managers when CCTV footage is stopped, offline, or deleted.<br />
              <strong>2. Automated Attendance:</strong> Accurately tracks when staff enter and leave without human data entry or paper registers.<br />
              <strong>3. Ready for Existing Hardware:</strong> Delivers high-speed AI tracking on standard port IT computers with zero GPU hardware cost.
            </p>

            {/* Formal 2-Column Sign-Off Block */}
            <div className="grid grid-cols-2 gap-4 text-[9.5px]">
              <div className="rounded border border-slate-300 p-2 bg-slate-50">
                <span className="font-bold text-slate-700 uppercase tracking-wider text-[8.5px] block mb-0.5">Prepared By:</span>
                <div className="h-7 border-b border-dashed border-slate-400 flex items-center justify-center font-serif italic text-amber-900 text-xs">
                  Sentinel AI Solutions Team
                </div>
                <div className="flex justify-between items-center text-slate-600 text-[8.5px] mt-1 font-mono">
                  <span>Batch: DBGT POC Demo</span>
                  <span>Date: 17 Oct 2026</span>
                </div>
              </div>

              <div className="rounded border border-slate-300 p-2 bg-slate-50">
                <span className="font-bold text-slate-700 uppercase tracking-wider text-[8.5px] block mb-0.5">Acknowledged By:</span>
                <div className="h-7 border-b border-dashed border-slate-400 flex items-center justify-center text-slate-400 font-sans text-xs">
                  (Authorized Signature / DBGT Terminal Operations)
                </div>
                <div className="flex justify-between items-center text-slate-600 text-[8.5px] mt-1 font-mono">
                  <span>Terminal: Dakshin Bharat Gateway Terminal</span>
                  <span>Status: POC COMPLETED</span>
                </div>
              </div>
            </div>

            {/* Page 2 Footer */}
            <div className="mt-3 pt-1.5 border-t border-slate-300 flex justify-between items-center text-[8.5px] font-mono text-slate-500">
              <span>SENTINEL-EVAL-DBGT-20261017-01</span>
              <span>END OF OFFICIAL POC REPORT — DAKSHIN BHARAT GATEWAY TERMINAL</span>
              <span>Page 2 of 2</span>
            </div>
          </div>

        </section>

      </main>
    </div>
  )
}
