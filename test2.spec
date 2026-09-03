Name: testpkg
Version: 1.0
Release: 1%{?dist}
Summary: Test
License: MIT
BuildArch: x86_64
Source0: %{name}-%{version}.tar.gz

%global debug_package %{nil}
%undefine _missing_build_ids_terminate_build

%description
Test.

%prep
%setup -q -c -T

%install
mkdir -p %{buildroot}/usr/bin
gcc -Wl,--build-id=none -x c -o %{buildroot}/usr/bin/testelf - <<EOC
int main(){return 0;}
EOC

%files
/usr

%changelog
* Wed Sep 03 2026 Test <test@example.com> - 1.0-1
- init
