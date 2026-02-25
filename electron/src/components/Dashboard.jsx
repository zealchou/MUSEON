/**
 * Token Dashboard Component
 *
 * Features:
 * - Today's token consumption
 * - Monthly cumulative usage
 * - Model distribution (Haiku vs Sonnet)
 * - 30-day trend chart
 * - Budget progress
 * - Estimated monthly bill
 */

import React, { useState, useEffect } from 'react';
import { Line, Doughnut, Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  ArcElement,
  BarElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  ArcElement,
  BarElement,
  Title,
  Tooltip,
  Legend
);

const Dashboard = () => {
  const [tokenData, setTokenData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadTokenData();

    // Refresh every 30 seconds
    const interval = setInterval(loadTokenData, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadTokenData = async () => {
    try {
      const response = await window.museclaw.queryGateway('show token dashboard data');
      setTokenData(response);
      setLoading(false);
      setError(null);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner"></div>
        <p>Loading token data...</p>
      </div>
    );
  }

  if (error) {
    return <div className="error">Error loading token data: {error}</div>;
  }

  if (!tokenData) {
    return <div className="error">No token data available</div>;
  }

  // Calculate budget percentage
  const budgetPercentage = (tokenData.monthlyUsage / tokenData.monthlyBudget) * 100;
  const budgetClass = budgetPercentage > 80 ? 'warning' : '';

  // Trend chart data (last 30 days)
  const trendData = {
    labels: tokenData.dailyTrend.map(d => d.date),
    datasets: [
      {
        label: 'Daily Tokens',
        data: tokenData.dailyTrend.map(d => d.tokens),
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        tension: 0.4
      }
    ]
  };

  const trendOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false
      },
      tooltip: {
        callbacks: {
          label: (context) => `${context.parsed.y.toLocaleString()} tokens`
        }
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        grid: {
          color: '#334155'
        },
        ticks: {
          color: '#94a3b8'
        }
      },
      x: {
        grid: {
          color: '#334155'
        },
        ticks: {
          color: '#94a3b8'
        }
      }
    }
  };

  // Model distribution chart
  const modelData = {
    labels: ['Haiku', 'Sonnet'],
    datasets: [
      {
        data: [tokenData.haikuPercentage, tokenData.sonnetPercentage],
        backgroundColor: ['#10b981', '#3b82f6'],
        borderWidth: 0
      }
    ]
  };

  const modelOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          color: '#e2e8f0'
        }
      },
      tooltip: {
        callbacks: {
          label: (context) => `${context.label}: ${context.parsed}%`
        }
      }
    }
  };

  // Top scenarios
  const scenarioData = {
    labels: tokenData.topScenarios.map(s => s.name),
    datasets: [
      {
        label: 'Tokens Used',
        data: tokenData.topScenarios.map(s => s.tokens),
        backgroundColor: '#8b5cf6'
      }
    ]
  };

  const scenarioOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false
      },
      tooltip: {
        callbacks: {
          label: (context) => `${context.parsed.y.toLocaleString()} tokens`
        }
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        grid: {
          color: '#334155'
        },
        ticks: {
          color: '#94a3b8'
        }
      },
      x: {
        grid: {
          display: false
        },
        ticks: {
          color: '#94a3b8'
        }
      }
    }
  };

  return (
    <div className="dashboard">
      {/* Summary Stats */}
      <div className="card" style={{ gridColumn: '1 / -1' }}>
        <h2 className="card-title">Token Usage Summary</h2>
        <div className="stat-grid">
          <div className="stat-item">
            <div className="stat-label">Today's Consumption</div>
            <div className="stat-value">
              {tokenData.todayTokens.toLocaleString()}
            </div>
            <div className="stat-label">${tokenData.todayCost.toFixed(2)}</div>
          </div>
          <div className="stat-item">
            <div className="stat-label">Monthly Total</div>
            <div className={`stat-value ${budgetClass}`}>
              {tokenData.monthlyUsage.toLocaleString()}
            </div>
            <div className="stat-label">${tokenData.monthlyCost.toFixed(2)}</div>
          </div>
          <div className="stat-item">
            <div className="stat-label">Monthly Budget</div>
            <div className="stat-value">
              {tokenData.monthlyBudget.toLocaleString()}
            </div>
            <div className="progress-bar">
              <div
                className={`progress-fill ${budgetClass}`}
                style={{ width: `${Math.min(budgetPercentage, 100)}%` }}
              ></div>
            </div>
            <div className="stat-label">{budgetPercentage.toFixed(1)}% used</div>
          </div>
          <div className="stat-item">
            <div className="stat-label">Estimated Monthly Bill</div>
            <div className={`stat-value ${budgetPercentage > 90 ? 'danger' : budgetClass}`}>
              ${tokenData.estimatedBill.toFixed(2)}
            </div>
            <div className="stat-label">
              {tokenData.estimatedBill > tokenData.expectedBill ? (
                <span style={{ color: '#ef4444' }}>
                  +${(tokenData.estimatedBill - tokenData.expectedBill).toFixed(2)} over
                </span>
              ) : (
                <span style={{ color: '#10b981' }}>
                  -${(tokenData.expectedBill - tokenData.estimatedBill).toFixed(2)} under
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 30-Day Trend */}
      <div className="card" style={{ gridColumn: 'span 2' }}>
        <h2 className="card-title">30-Day Token Usage Trend</h2>
        <div className="chart-container">
          <Line data={trendData} options={trendOptions} />
        </div>
      </div>

      {/* Model Distribution */}
      <div className="card">
        <h2 className="card-title">Model Distribution</h2>
        <div className="chart-container">
          <Doughnut data={modelData} options={modelOptions} />
        </div>
        <div style={{ marginTop: '1rem', textAlign: 'center', fontSize: '0.875rem', color: '#94a3b8' }}>
          Haiku: {tokenData.haikuPercentage}% | Sonnet: {tokenData.sonnetPercentage}%
        </div>
      </div>

      {/* Top 5 Token Consumers */}
      <div className="card" style={{ gridColumn: 'span 2' }}>
        <h2 className="card-title">Top 5 Token Consuming Scenarios</h2>
        <div className="chart-container">
          <Bar data={scenarioData} options={scenarioOptions} />
        </div>
      </div>

      {/* Optimization History */}
      {tokenData.optimizationHistory && tokenData.optimizationHistory.length > 0 && (
        <div className="card" style={{ gridColumn: '1 / -1' }}>
          <h2 className="card-title">Recent Token Optimizations</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Optimization</th>
                <th>Tokens Saved</th>
                <th>Cost Saved</th>
              </tr>
            </thead>
            <tbody>
              {tokenData.optimizationHistory.map((opt, idx) => (
                <tr key={idx}>
                  <td>{opt.date}</td>
                  <td>{opt.description}</td>
                  <td style={{ color: '#10b981' }}>
                    -{opt.tokensSaved.toLocaleString()}
                  </td>
                  <td style={{ color: '#10b981' }}>
                    -${opt.costSaved.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
