import React, { useState, useEffect } from 'react';
import { useDispatch } from 'react-redux';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  Button, Input, Label, Alert, AlertDescription,
  Tabs, TabsContent, TabsList, TabsTrigger, Separator
} from '../ui';
import {
  LogIn, UserPlus, ShoppingCart, AlertCircle, Mail, Lock, User, X
} from 'lucide-react';
import SocialLoginButtons from '../auth/SocialLoginButtons';
import { useLoginMutation, useRegisterMutation } from '../../store/api/user.api';
import { setUser, loadUserProfile } from '../../store/authSlice';
import { useAuth } from '../../auth/AuthProvider';
import { useToast } from '../../hooks/use-toast';

const CheckoutAuthModal = ({ open, onClose, onContinueAsGuest, onAuthSuccess }) => {
  const dispatch = useDispatch();
  const { isAuthenticated } = useAuth();
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState('login');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  // Redux RTK Query hooks
  const [loginMutation] = useLoginMutation();
  const [registerMutation] = useRegisterMutation();
  
  // Login form state
  const [loginData, setLoginData] = useState({
    email: '',
    password: ''
  });
  
  // Register form state
  const [registerData, setRegisterData] = useState({
    email: '',
    password: '',
    confirmPassword: '',
    full_name: '',
    role: 'buyer'
  });

  // Close modal if user becomes authenticated
  useEffect(() => {
    if (isAuthenticated && open) {
      if (onAuthSuccess) {
        onAuthSuccess();
      }
      onClose();
    }
  }, [isAuthenticated, open, onClose, onAuthSuccess]);

  // Handle login
  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const data = await loginMutation({
        email: loginData.email.trim(),
        password: loginData.password
      }).unwrap();
      
      // Store token and user data
      if (data.access_token) {
        localStorage.setItem('token', data.access_token);
      }
      if (data.user) {
        localStorage.setItem('user', JSON.stringify(data.user));
        dispatch(setUser(data.user));
      }
      
      // Refresh auth state
      await dispatch(loadUserProfile(true));
      
      toast({
        title: "Login Successful!",
        description: "Welcome back! Redirecting to checkout...",
      });
      
      if (onAuthSuccess) {
        onAuthSuccess();
      }
      onClose();

    } catch (error) {
      console.error('Login error:', error);
      setError(error?.data?.detail || error?.message || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  // Handle register
  const handleRegister = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      // Validate passwords match
      if (registerData.password !== registerData.confirmPassword) {
        throw new Error('Passwords do not match');
      }

      if (registerData.password.length < 6) {
        throw new Error('Password must be at least 6 characters');
      }

      const data = await registerMutation({
        email: registerData.email.trim(),
        password: registerData.password,
        full_name: registerData.full_name.trim(),
        role: registerData.role
      }).unwrap();
      
      // Store token and user data
      if (data.access_token) {
        localStorage.setItem('token', data.access_token);
      }
      if (data.user) {
        localStorage.setItem('user', JSON.stringify(data.user));
        dispatch(setUser(data.user));
      }
      
      // Refresh auth state
      await dispatch(loadUserProfile(true));
      
      toast({
        title: "Registration Successful!",
        description: "Account created! Redirecting to checkout...",
      });
      
      if (onAuthSuccess) {
        onAuthSuccess();
      }
      onClose();

    } catch (error) {
      console.error('Register error:', error);
      setError(error?.data?.detail || error?.message || 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleContinueAsGuest = () => {
    if (onContinueAsGuest) {
      onContinueAsGuest();
    }
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <ShoppingCart className="h-6 w-6 text-emerald-600" />
            Complete Your Checkout
          </DialogTitle>
          <DialogDescription>
            Sign in to your account for faster checkout, order tracking, and exclusive deals. 
            Or continue as a guest to complete your purchase.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="login" className="flex items-center gap-2">
              <LogIn className="h-4 w-4" />
              Sign In
            </TabsTrigger>
            <TabsTrigger value="register" className="flex items-center gap-2">
              <UserPlus className="h-4 w-4" />
              Create Account
            </TabsTrigger>
          </TabsList>

          {/* Login Tab */}
          <TabsContent value="login" className="space-y-4 mt-4">
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <Label htmlFor="login-email">Email Address</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <Input
                    id="login-email"
                    type="email"
                    className="pl-10"
                    value={loginData.email}
                    onChange={(e) => setLoginData(prev => ({...prev, email: e.target.value}))}
                    placeholder="your@email.com"
                    required
                    disabled={loading}
                  />
                </div>
              </div>

              <div>
                <Label htmlFor="login-password">Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <Input
                    id="login-password"
                    type="password"
                    className="pl-10"
                    value={loginData.password}
                    onChange={(e) => setLoginData(prev => ({...prev, password: e.target.value}))}
                    placeholder="Enter your password"
                    required
                    disabled={loading}
                  />
                </div>
              </div>

              <Button 
                type="submit" 
                className="w-full bg-emerald-600 hover:bg-emerald-700" 
                disabled={loading}
              >
                {loading ? 'Signing in...' : 'Sign In'}
              </Button>
            </form>

            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <Separator />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-background px-2 text-muted-foreground">Or continue with</span>
              </div>
            </div>

            <SocialLoginButtons 
              onSuccess={(data) => {
                if (onAuthSuccess) {
                  onAuthSuccess();
                }
                onClose();
              }}
            />
          </TabsContent>

          {/* Register Tab */}
          <TabsContent value="register" className="space-y-4 mt-4">
            <form onSubmit={handleRegister} className="space-y-4">
              <div>
                <Label htmlFor="register-name">Full Name</Label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <Input
                    id="register-name"
                    type="text"
                    className="pl-10"
                    value={registerData.full_name}
                    onChange={(e) => setRegisterData(prev => ({...prev, full_name: e.target.value}))}
                    placeholder="John Doe"
                    required
                    disabled={loading}
                  />
                </div>
              </div>

              <div>
                <Label htmlFor="register-email">Email Address</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <Input
                    id="register-email"
                    type="email"
                    className="pl-10"
                    value={registerData.email}
                    onChange={(e) => setRegisterData(prev => ({...prev, email: e.target.value}))}
                    placeholder="your@email.com"
                    required
                    disabled={loading}
                  />
                </div>
              </div>

              <div>
                <Label htmlFor="register-password">Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <Input
                    id="register-password"
                    type="password"
                    className="pl-10"
                    value={registerData.password}
                    onChange={(e) => setRegisterData(prev => ({...prev, password: e.target.value}))}
                    placeholder="At least 6 characters"
                    required
                    minLength={6}
                    disabled={loading}
                  />
                </div>
              </div>

              <div>
                <Label htmlFor="register-confirm-password">Confirm Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <Input
                    id="register-confirm-password"
                    type="password"
                    className="pl-10"
                    value={registerData.confirmPassword}
                    onChange={(e) => setRegisterData(prev => ({...prev, confirmPassword: e.target.value}))}
                    placeholder="Confirm your password"
                    required
                    minLength={6}
                    disabled={loading}
                  />
                </div>
              </div>

              <Button 
                type="submit" 
                className="w-full bg-emerald-600 hover:bg-emerald-700" 
                disabled={loading}
              >
                {loading ? 'Creating account...' : 'Create Account'}
              </Button>
            </form>

            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <Separator />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-background px-2 text-muted-foreground">Or continue with</span>
              </div>
            </div>

            <SocialLoginButtons 
              onSuccess={(data) => {
                if (onAuthSuccess) {
                  onAuthSuccess();
                }
                onClose();
              }}
            />
          </TabsContent>
        </Tabs>

        <Separator />

        <div className="space-y-3">
          <Button
            variant="outline"
            className="w-full border-emerald-300 text-emerald-700 hover:bg-emerald-50"
            onClick={handleContinueAsGuest}
            disabled={loading}
          >
            Continue as Guest
          </Button>
          <p className="text-xs text-center text-gray-500">
            You can create an account later to track your orders and save your information.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default CheckoutAuthModal;

